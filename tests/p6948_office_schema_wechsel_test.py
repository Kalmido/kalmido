#!/usr/bin/env python3
# kalmido-suite: fresh now=2027-01-05T09:00:00Z
"""2.1365.0 API tests (#6948): the change of the number schemes at the turn of the year 2026 -> 2027, played through with a copy
of a long-running office's settings (the server's test clock stands on 5 January 2027; the documents of December 2026 are
made with their December dates). Invented companies, people and figures only.
freelancer-matrix: office
Before: invoices {seq}_{kuerzel}_{isodate}_R, corrections on the invoices' counter (credit_shared) as ..._RK, the legacy program
up to 672 (the counter set to 673 with a reason). From 1 January: invoices GS-{yyyy}-{seq:03}, corrections GS-{yyyy}-{seq:03}-K
on the same counter, an additional number range GT-{yyyy}-{seq:03} (#6698, corrections -K). Once in an organisation's office,
once in the personal office of a person without an organisation:
 (1) the new schemes are taken by the settings; the hash chain stays intact, no date order error
 (2) the first invoice of 2027 is GS-2027-001, its correction GS-2027-002-K on the same counter
 (3) a draft of December finalised in January: with the date set to the day of finalising GS-2027-003; a draft that keeps its
     December date gets the number of its own year (GS-2026-001, a counter of 2026 under the new scheme) -- the finalise
     dialog's preview names exactly that number before
 (4) the correction of a December invoice (old form) in January gets a 2027 number and points at that invoice (cancels,
     the e-invoice's BT-25)
 (5) GT counts apart: GT-2027-001 next to the GS numbers, neither counter moves the other
 (6) the DATEV batch (December and January), the income statement 2027 (payments in January for both forms) and the e-invoice
     XML handle both forms in the same year
usage: p6948_office_schema_wechsel_test.py <datadir>"""
import os
import re
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check  # noqa: E402
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from testclock import today  # noqa: E402

kt.docker_logs_on_first_fail()
OF = "/api/office"
D = OF + "/docs"
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "phone": "+49 40 1234567", "tax_number": "12/345/67890", "vat_id": "DE999999999",
           "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}
OLD = {"invoice_scheme": "{seq}_{kuerzel}_{isodate}_R", "credit_shared": 1, "credit_scheme": "{seq}_{kuerzel}_{isodate}_RK"}
NEW = {"invoice_scheme": "GS-{yyyy}-{seq:03}", "credit_shared": 1, "credit_scheme": "GS-{yyyy}-{seq:03}-K"}
TODAY = today()


def beleg(number):  # DATEV Belegfeld 1 (office/datev.py dx_beleg)
    return re.sub(r"[^A-Za-z0-9$&%*+\-/]", "-", number or "").lstrip("+-")[:36]


A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A)
check(TODAY.isoformat() == "2027-01-05", f"the test clock stands on 5 January 2027 ({TODAY})")


def run(S, who):
    def ok(cond, what):
        return check(cond, f"{who}: {what}")

    r = S.put(B + OF + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "de", "currency": "EUR", "payment_days": 14,
                                        "company_fields": COMPANY, **OLD,
                                        "datev_extf": {"advisor_no": "1234567", "client_no": "12345", "fy_start": 1, "acct_len": 4, "chart": "SKR03"}})
    ok(r.ok, "the settings of the long-running office " + r.text[:200])
    r = S.post(B + OF + "/number-ranges/invoice", json={"next": 673, "reason": "Altsystem bis 672"})
    ok(r.ok and r.json().get("next") == 673, "the legacy program up to 672 " + r.text[:160])
    cl = S.post(B + "/api/clients", json={"name": "Testkunde Nord", "short_code": "TKN", "street": "Marktstraße 5", "zip": "50667", "city": "Köln",
                                          "country": "DE", "vat_id": "DE811111111", "email_invoice": "rechnung@testkunde.example"})
    assert cl.status_code == 201, cl.text
    CL = cl.json()["id"]

    def draft(day, **kw):
        r = S.post(B + D, json={"kind": "invoice", "client_id": CL, "date": day, "service_from": "2026-12-01", "service_to": "2026-12-31",
                                "items": [{"title": "Tarif Studio, Dezember 2026", "qty": 1, "rate": 150, "unit": "piece"}], **kw})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def fin(did):
        r = S.post(B + f"{D}/{did}/finalize", json={})
        ok(r.ok, f"finalised #{did} {r.text[:240]}")
        return (r.json() if r.ok else {}).get("number") or ""

    def chain_ok(when):
        ch = S.get(B + OF + "/log/chain").json()
        ok(ch.get("ok") is True and ch.get("pending") == 0, f"{when}: the hash chain intact {ch}")

    # ---------------------------------------------------------------- December 2026, the old schemes
    i1, i2 = draft("2026-12-10"), draft("2026-12-15")
    n1, n2 = fin(i1), fin(i2)
    ok((n1, n2) == ("673_TKN_2026-12-10_R", "674_TKN_2026-12-15_R"), f"December: the old form continues after 672 {n1} {n2}")
    dec_a, dec_b = draft("2026-12-20"), draft("2026-12-22")  # drafts of December, finalised in January below
    chain_ok("December")

    # ---------------------------------------------------------------- (1) the change of the schemes
    r = S.put(B + OF + "/settings", json=NEW)
    s = S.get(B + OF + "/settings").json().get("settings") or {}
    ok(r.ok and all(s.get(k) == v for k, v in NEW.items()), f"(1) the new schemes are taken {r.status_code} {r.text[:200]}")
    rg = {x["kind"]: x for x in S.get(B + OF + "/number-ranges").json()["ranges"]}
    ok(rg["invoice"]["next"] == 1 and rg["invoice"]["period"] == "2027" and rg["credit"].get("shared") == "invoice",
       f"(1) the page: the counter of 2027 starts at 1, the corrections count with the invoices {rg['invoice']} {rg['credit']}")

    # ---------------------------------------------------------------- (2) the first invoice of 2027 and its correction
    j1 = draft(TODAY.isoformat())
    nj1 = fin(j1)
    ok(nj1 == "GS-2027-001", f"(2) the first invoice of 2027 {nj1}")
    r = S.post(B + f"{D}/{j1}/credit", json={})
    ok(r.status_code == 201, "(2) correction draft " + r.text[:160])
    k1 = r.json()["id"]
    nk1 = fin(k1)
    ok(nk1 == "GS-2027-002-K", f"(2) its correction on the same counter with -K {nk1}")

    # ---------------------------------------------------------------- (3) the drafts of December
    ok(S.patch(B + f"{D}/{dec_a}", json={"date": TODAY.isoformat()}).ok, "(3) the December draft takes the day of finalising")
    na = fin(dec_a)
    ok(na == "GS-2027-003", f"(3) ... and the number of 2027 {na}")
    pv = S.get(B + f"{D}/{dec_b}/number-preview").json().get("number")
    ok(pv == "GS-2026-001", f"(3) a draft keeping its December date: the dialog names the number of its year before {pv}")
    nb = fin(dec_b)
    ok(nb == pv, f"(3) ... and it gets exactly that one {nb}")
    chain_ok("(3)")

    # ---------------------------------------------------------------- (4) the correction of a December invoice
    r = S.post(B + f"{D}/{i1}/credit", json={})
    ok(r.status_code == 201, "(4) correction draft of the December invoice " + r.text[:160])
    k2 = r.json()["id"]
    nk2 = fin(k2)
    ok(nk2 == "GS-2027-004-K", f"(4) a 2027 number {nk2}")
    k2d = S.get(B + f"{D}/{k2}").json()
    ok(k2d.get("cancels_id") == i1 and (k2d.get("cancels") or {}).get("number") == n1 and k2d.get("date") == TODAY.isoformat(),
       f"(4) it points at the December invoice {k2d.get('cancels_id')} {k2d.get('cancels')} {k2d.get('date')}")

    # ---------------------------------------------------------------- (5) GT counts apart
    r = S.post(B + "/api/office/num-ranges", json={"code": "GT", "name": "Plattform", "scheme": "GT-{yyyy}-{seq:03}", "credit_suffix": "-K"})
    ok(r.status_code == 201, "(5) the range GT " + r.text[:160])
    G = r.json().get("id")
    g1 = draft("2026-12-28", range_id=G)
    ng = fin(g1)
    ok(ng == "GT-2027-001", f"(5) GT-2027-001 next to the GS numbers (date set by Kalmido) {ng}")
    rg = {x["kind"]: x for x in S.get(B + OF + "/number-ranges").json()["ranges"]}
    ok(rg["invoice"]["next"] == 5, f"(5) the GS counter did not move {rg['invoice']['next']}")
    j2 = draft(TODAY.isoformat())
    ok(fin(j2) == "GS-2027-005", "(5) the next GS invoice after GT")
    chain_ok("(5)")

    # ---------------------------------------------------------------- (6) DATEV, income statement, e-invoice
    for did, day in ((i2, TODAY.isoformat()), (j2, TODAY.isoformat()), (g1, TODAY.isoformat())):
        r = S.post(B + f"{D}/{did}/payments", json={"date": day, "amount": S.get(B + f"{D}/{did}").json()["open"], "method": "transfer"})
        ok(r.ok, f"(6) payment in January {r.text[:160]}")
    for frm, to, want in (("2026-12-01", "2026-12-31", [n1, n2, nb]), ("2027-01-01", "2027-01-31", [nj1, nk1, na, nk2, ng, "GS-2027-005"])):
        r = S.get(B + OF + f"/datev/extf?from={frm}&to={to}")
        ok(r.ok, f"(6) DATEV batch {frm} {r.status_code} {r.text[:200]}")
        if not r.ok:
            continue
        rows = r.content.decode("cp1252").split("\r\n")
        cols = [x.strip('"') for x in rows[1].split(";")] if len(rows) > 1 else []
        recs = [{k: v.strip('"') for k, v in zip(cols, x.split(";"))} for x in rows[2:] if x]
        fields = {x.get("Belegfeld 1") for x in recs}
        ok(all(beleg(n) in fields for n in want), f"(6) DATEV {frm[:7]}: every document with its number in Belegfeld 1 {sorted(fields)} {want}")
    eu = S.get(B + OF + "/books/euer?year=2027").json()
    v19 = next((x for x in eu.get("income", []) if x.get("key") == "vat19"), {})
    ok(v19.get("net") == "450.00", f"(6) income statement 2027: the payments of January for both forms (674_..._R, GS-2027-005, GT-2027-001) {eu.get('income')}")
    for did, num in ((j2, "GS-2027-005"), (k2, nk2), (i1, n1)):
        r = S.get(B + f"{D}/{did}/xml")
        x = r.text if r.ok else ""
        ok(r.ok and f"<ram:ID>{num}</ram:ID>" in x, f"(6) e-invoice of {num} {r.status_code} {x[:120]}")
    x = S.get(B + f"{D}/{k2}/xml").text
    ok("<ram:InvoiceReferencedDocument>" in x and f"<ram:IssuerAssignedID>{n1}</ram:IssuerAssignedID>" in x,
       "(6) the correction's e-invoice names the December invoice (BT-25)")
    chain_ok("end")


run(A, "org")
Fr.patch(B + "/api/settings", json={"workspace": "private"})
run(Fr, "private")
sys.exit(kt.done("p6948_office_schema_wechsel"))
