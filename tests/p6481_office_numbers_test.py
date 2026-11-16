#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1289.0 API tests (#6481, audit #4791 N2 N3 N4 S2 S3 U4): numbers of Office & finance, once in the personal office of a
person without an organisation (freelancer fixture; freelancer-matrix: office) and once in an organisation's office (its
admin; a plain member for the rights). Invented companies and people only.
 - N2 a value the counter passes because a quotation or the legacy archive carries it is an office log line number (skipped,
   "taken by ..."); more than 50 taken values in a row are counted past (was: "already used"); the finalise dialog's preview
   shows the free one. A quotation number by hand that follows the invoice / correction scheme: 400; an older quotation with
   such a number stays changeable
 - N4 {isodate} / {date} of a number by hand are checked against the document date (409), like {yyyy}
 - S2 a correction never dates before its invoice (400 naming the invoice), with the corrections' own counter
 - N3/S3 an invoice / correction takes a number by hand only with the finalising (POST .../finalize {number, reason}; the
   draft route: 409, a plain member: 403, a quotation: 400); a numbered draft from before is marked in the list and the view
   (number_draft), stays finalisable; a numbered correction draft's delete text names no cancellation
 - U4 a finalised document with the import's log line is marked imported (at, by) in the list, the view and the auditor's
   export (invoices.csv Importiert_am / Importiert_von)
usage: p6481_office_numbers_test.py <datadir>"""
import csv
import io
import os
import sys
import zipfile
from datetime import date, timedelta

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess  # noqa: E402
import dbx as dbxm  # noqa: E402
import requests  # noqa: E402

B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
OFF_API = "/api/office"
D = OFF_API + "/docs"
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "tax_number": "12/345/67890", "vat_id": "DE999999999",
           "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}


def dbx(sql, args=()):
    c = dbxm.connect(os.path.join(sys.argv[1], "tasks.db"), timeout=10)
    try:
        cur = c.execute(sql, args)
        try:
            rows = cur.fetchall()
        except Exception:  # noqa: BLE001 -- a write without rows
            rows = []
        c.commit()
        return rows
    finally:
        c.close()


s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en"})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob Member", "password": "password123", "email": "bob@example.com"})
assert r.ok, r.text
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
assert A.put(B + f"/api/orgs/{ORG}/members", json={"email": "bob@example.com", "role": "member"}).ok
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
Bo = sess("bob")
Bo.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A)


def run(S, who, member=None):
    def ok(cond, what):
        check(cond, f"{who}: {what}")

    r = S.put(B + OFF_API + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "de", "currency": "EUR", "payment_days": 14,
                                         "company_fields": COMPANY, "offer_scheme": "KVA-{yyyy}-{seq:03}",
                                         "invoice_scheme": "RE-{yyyy}-{seq:03}", "credit_scheme": "RK-{yyyy}-{seq:03}"})
    ok(r.ok, "office settings " + r.text[:200])
    me = S.get(B + "/api/state").json()["me"]
    cl = S.post(B + "/api/clients", json={"name": "Testkunde Nord", "street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE"})
    assert cl.status_code == 201, cl.text
    CL = cl.json()["id"]

    def invoice(**kw):
        r = S.post(B + D, json={"kind": "invoice", "client_id": CL, "service_from": "2026-10-01", "service_to": "2026-10-20",
                                "items": [{"title": "Schnitt", "qty": 1, "rate": 100, "unit": "piece"}], **kw})
        assert r.status_code == 201, r.text
        return r.json()

    def finalize(did, body=None):
        return S.post(B + f"{D}/{did}/finalize", json=body or {})

    def nxt(kind="invoice"):
        return {x["kind"]: x for x in S.get(B + OFF_API + "/number-ranges").json()["ranges"]}[kind]["next"]

    def skipped():
        return [x["detail"] for x in S.get(B + OFF_API + "/log?limit=500").json().get("log", []) if x["action"] == "number" and "skipped" in (x.get("detail") or {})]

    Y = date.fromisoformat(invoice()["date"]).year
    re_ = lambda n: f"RE-{Y}-{n:03d}"  # noqa: E731

    # ---------------------------------------------------------------- N2 a quotation never takes a number of the invoice series
    off = S.post(B + D, json={"kind": "offer", "client_id": CL, "items": [{"title": "Kamera", "qty": 1, "rate": 500}]}).json()
    for bad in (re_(5), f"RK-{Y}-002"):
        r = S.post(B + f"{D}/{off['id']}/number", json={"number": bad})
        ok(r.status_code == 400 and "a number of its own" in r.json().get("error", ""), f"N2: quotation number {bad} of the invoice / correction series: 400 " + r.text[:160])
    r = S.post(B + f"{D}/{off['id']}/number", json={"number": "KVA-FREI-1"})
    ok(r.ok and r.json()["number"] == "KVA-FREI-1", "N2: a quotation number of its own is fine " + r.text[:120])
    # an older quotation (before 2.1289) with the next invoice number: changeable; the invoice counter passes it with a log line
    n = nxt()
    dbx("UPDATE office_docs SET number=? WHERE id=?", (re_(n), off["id"]))
    ok(S.patch(B + f"{D}/{off['id']}", json={"project_title": "Weiter änderbar"}).ok, "N2: the older quotation with such a number stays changeable")
    ok(S.post(B + f"{D}/{off['id']}/number", json={"number": re_(n)}).ok, "N2: ... and keeps its number when it is sent again")
    before = len(skipped())
    i1 = invoice()
    r = finalize(i1["id"])
    ok(r.ok and r.json()["number"] == re_(n + 1), f"N2: the invoice gets the next free number {re_(n + 1)}: " + r.text[:160])
    sk = skipped()
    ok(len(sk) == before + 1 and sk[0]["skipped"] == re_(n) and f"#{off['id']}" in sk[0].get("reason", ""),
       f"N2: the skipped {re_(n)} is an office log line naming the quotation {sk[:1]}")
    # numbers of the legacy archive: counted past (also more than 50 in a row), each one logged; the preview shows the free one
    oid = dbx("SELECT org_id FROM office_docs WHERE id=?", (i1["id"],))[0][0]
    n = nxt()
    for k in range(n, n + 60):
        dbx("INSERT INTO office_archive(org_id, kind, number, created_at) VALUES(?,?,?,now())", (oid, "invoice", re_(k)))
    i2 = invoice()
    pv = S.get(B + f"{D}/{i2['id']}/number-preview").json()
    ok(pv.get("number") == re_(n + 60), f"N2: the finalise dialog names the first free number {re_(n + 60)}: {pv}")
    before = len(skipped())
    r = finalize(i2["id"])
    ok(r.ok and r.json()["number"] == re_(n + 60), f"N2: 60 numbers of the legacy archive in a row are counted past (was: already used) {re_(n + 60)}: " + r.text[:160])
    sk = skipped()
    ok(len(sk) == before + 60 and {x["skipped"] for x in sk[:60]} == {re_(k) for k in range(n, n + 60)} and all(x.get("reason") for x in sk[:60]),
       f"N2: every skipped archive number is logged with its reason ({len(sk) - before})")

    # ---------------------------------------------------------------- N4 {isodate} / {date} of a number by hand = the document date
    for sch, fmt in (("{seq}_{isodate}_R", "%Y-%m-%d"), ("{seq}-{date}-R", "%Y%m%d")):
        ok(S.put(B + OFF_API + "/settings", json={"invoice_scheme": sch}).ok, f"N4: scheme {sch}")
        inv = invoice()
        day = date.fromisoformat(inv["date"])
        k = nxt()
        wrong = sch.replace("{seq}", str(k)).replace("{isodate}" if "iso" in sch else "{date}", date(2020, 1, 1).strftime(fmt))
        r = finalize(inv["id"], {"number": wrong})
        ok(r.status_code == 409 and "carries the date" in r.json().get("error", ""), f"N4: {wrong} for a document of {day}: 409 " + r.text[:160])
        right = sch.replace("{seq}", str(k)).replace("{isodate}" if "iso" in sch else "{date}", day.strftime(fmt))
        r = finalize(inv["id"], {"number": right})
        ok(r.ok and r.json()["number"] == right, f"N4: {right} with the document's own date is taken " + r.text[:160])
    ok(S.put(B + OFF_API + "/settings", json={"invoice_scheme": "RE-{yyyy}-{seq:03}"}).ok, "back to the yearly scheme")

    # ---------------------------------------------------------------- S2 a correction never dates before its invoice
    inv = invoice()
    r = finalize(inv["id"])
    ok(r.ok, "S2: invoice finalised " + r.text[:120])
    num, day = r.json()["number"], date.fromisoformat(r.json()["date"])
    cr = S.post(B + f"{D}/{inv['id']}/credit").json()
    ok(S.patch(B + f"{D}/{cr['id']}", json={"date": (day - timedelta(days=1)).isoformat()}).ok, "S2: correction draft dated the day before")
    r = finalize(cr["id"])
    ok(r.status_code == 400 and "before the date of its invoice" in r.json().get("error", "") and num in r.json().get("error", ""),
       f"S2: a correction before its invoice {num}: 400 naming it " + r.text[:200])
    ok(S.patch(B + f"{D}/{cr['id']}", json={"date": day.isoformat()}).ok and finalize(cr["id"]).ok, "S2: with the invoice's date it is finalised")

    # ---------------------------------------------------------------- N3/S3 a number by hand only with the finalising
    inv = invoice()
    r = S.post(B + f"{D}/{inv['id']}/number", json={"number": re_(nxt())})
    ok(r.status_code == 409 and "finalise dialog" in r.json().get("error", ""), "N3: no number by hand at an invoice draft (409) " + r.text[:160])
    ok(S.get(B + f"{D}/{inv['id']}").json()["number"] == "", "N3: the draft stays without a number")
    if member is not None:
        r = member.post(B + f"{D}/{inv['id']}/finalize", json={"number": re_(nxt())})
        ok(r.status_code == 403 and not S.get(B + f"{D}/{inv['id']}").json()["locked"], "N3: a plain member finalises with a number by hand: 403 " + r.text[:120])
    k = nxt()
    r = finalize(inv["id"], {"number": re_(k + 2)})
    ok(r.status_code == 400 and "reason" in r.json().get("error", ""), "N3: a gap without a reason at finalising: 400 " + r.text[:160])
    ok(not S.get(B + f"{D}/{inv['id']}").json()["locked"] and nxt() == k, "N3: the refusal finalised nothing, no counter moved")
    r = finalize(inv["id"], {"number": re_(k + 2), "reason": "Zwei Nummern im Altprogramm vergeben"})
    ok(r.ok and r.json()["number"] == re_(k + 2) and r.json()["locked"] and nxt() == k + 3, "N3: finalised with the number by hand, the series follows " + r.text[:160])
    lg = [x for x in S.get(B + OFF_API + "/log?limit=50").json()["log"] if x["action"] == "number" and x.get("doc_id") == inv["id"]]
    ok(lg and lg[0]["detail"]["after"]["number"] == re_(k + 2) and "Altprogramm" in lg[0]["detail"]["after"].get("reason", ""), f"N3: the number and its reason are in the office log {lg[:1]}")
    cr = S.post(B + f"{D}/{inv['id']}/credit").json()
    r = S.post(B + f"{D}/{cr['id']}/number", json={"number": f"RK-{Y}-050"})
    ok(r.status_code == 409 and "finalise dialog" in r.json().get("error", ""), "S3: no number by hand at a correction draft (409) " + r.text[:160])
    ok(S.delete(B + f"{D}/{cr['id']}").ok, "S3: the correction draft without a number may go")
    r = finalize(off["id"], {"number": "KVA-FREI-9"})
    ok(r.status_code == 400, "N3: a quotation takes no number at finalising (400) " + r.text[:120])
    # a numbered draft from before 2.1289: marked in the list and the view, kept, finalisable with its number
    inv = invoice()
    old = re_(nxt())
    dbx("UPDATE office_docs SET number=? WHERE id=?", (old, inv["id"]))
    row = [x for x in S.get(B + D + "?kind=invoice").json()["docs"] if x["id"] == inv["id"]]
    ok(row and row[0].get("number_draft") is True, f"N3: the list marks the numbered invoice draft {row[:1]}")
    ok(S.get(B + f"{D}/{inv['id']}").json().get("number_draft") is True, "N3: the view marks it too")
    ok(not [x for x in S.get(B + D + "?kind=invoice").json()["docs"] if x.get("number_draft") and x["id"] != inv["id"]], "N3: no other row marked")
    ok(S.delete(B + f"{D}/{inv['id']}").status_code == 409, "N3: the numbered draft is kept")
    r = finalize(inv["id"], {"number": re_(nxt() + 5), "reason": "eine andere Nummer"})
    ok(r.status_code == 409 and old in r.json().get("error", ""), "N3: it keeps its number (another one at finalising: 409) " + r.text[:160])
    r = finalize(inv["id"])
    ok(r.ok and r.json()["number"] == old and not r.json().get("number_draft"), "N3: it is finalised with its number " + r.text[:160])
    cr = S.post(B + f"{D}/{inv['id']}/credit").json()
    dbx("UPDATE office_docs SET number=? WHERE id=?", (f"RK-{Y}-{nxt('credit'):03d}", cr["id"]))
    r = S.delete(B + f"{D}/{cr['id']}")
    e = r.json().get("error", "")
    ok(r.status_code == 409 and "new invoice" in e and "cancel it" not in e, "S3: a numbered correction draft: kept, the text names a way that exists " + e[:200])
    ok(finalize(cr["id"]).ok, "S3: ... and it can be finalised")

    # ---------------------------------------------------------------- U4 imported finalised documents are marked
    inv = invoice()
    num = finalize(inv["id"]).json()["number"]
    dbx("INSERT INTO office_doc_log(org_id, doc_id, user_id, at, action, target, detail) VALUES(?,?,?,?,?,?,?)",
        (oid, inv["id"], me["id"], "2026-11-01T10:00:00Z", "import", "doc", '{"source": "file"}'))
    row = [x for x in S.get(B + D + "?kind=invoice").json()["docs"] if x["id"] == inv["id"]]
    ok(row and (row[0].get("imported") or {}).get("at", "").startswith("2026-11-01") and row[0]["imported"].get("by") == me["display_name"],
       f"U4: the list row is marked imported (at, by) {row[:1]}")
    ok(not [x for x in S.get(B + D + "?kind=invoice").json()["docs"] if x.get("imported") and x["id"] != inv["id"]], "U4: no other row is marked imported")
    d = S.get(B + f"{D}/{inv['id']}").json()
    ok((d.get("imported") or {}).get("by") == me["display_name"], f"U4: the view is marked imported {d.get('imported')}")
    r = S.get(B + OFF_API + f"/gobd/export?from={Y}-01-01&to={date.fromisoformat(d['date']).isoformat()}")
    ok(r.ok, f"U4: auditor's export {r.status_code}")
    if r.ok:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        rows = list(csv.reader(io.StringIO(z.read("invoices.csv").decode("utf-8")), delimiter=";"))
        mine = [x for x in rows if x[2] == num]
        ok(mine and mine[0][-2:] == ["01.11.2026", me["display_name"]], f"U4: invoices.csv names import day and person {mine[:1]}")
        ok(all(x[-2:] == ["", ""] for x in rows if x[2] != num), "U4: the other invoices carry no import mark")
        ok(b"Importiert_am" in z.read("index.xml"), "U4: index.xml names the columns")


run(Fr, "freelancer")
run(A, "organisation", member=Bo)
print(f"p6481_office_numbers: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
