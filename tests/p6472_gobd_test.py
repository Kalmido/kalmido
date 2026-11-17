#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1315.0 API tests (#6472, audit #4791 A2 + N1): the auditor's export (GoBD) names the recipient as the invoice froze it
and every gap of the number series with its reason. Once in the personal office of a person without an organisation
(freelancer fixture; freelancer-matrix: office) and once in an organisation's office (its admin). Invented companies and
people only.
 - invoices.csv: Kunde / Kundennummer / Anschrift / USt_IdNr from recipient_snapshot -- the client renamed (new name, new
   customer number) after the invoice: the export keeps the old ones; the client gone (client_id NULL, as ON DELETE SET NULL):
   the name stays, Kundenstamm says there is none; Leistung_von / Leistung_bis / Faellig filled; a correction names the
   number of the invoice it cancels (Storno_von_Nummer); clients.csv says it is today's master
 - positions.csv: Steuerschluessel per position
 - number_ranges.csv (in index.xml): per series and period the counter and every missing number as a range with one reason:
   "1-672: Startnummer: <reason>" (the counter set on the number ranges page), a numbered draft "Entwurf traegt die Nummer",
   the run below a number set by hand "Nummer von Hand: <reason>", a counter moved without a log line "ohne Grund"
 - the number ranges page names the same gaps (gaps.count, gaps.none, the reasons)
usage: p6472_gobd_test.py <datadir>"""
import csv
import io
import os
import re
import sys
import zipfile
from datetime import date

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


def tables(z):
    """{url: [column names]} of index.xml."""
    x = z.read("index.xml").decode("utf-8")
    out = {}
    for m in re.finditer(r"<Table>(.*?)</Table>", x, re.S):
        url = re.search(r"<URL>([^<]*)</URL>", m.group(1)).group(1)
        out[url] = re.findall(r"<Variable(?:PrimaryKey|Column)><Name>([^<]*)</Name>", m.group(1))
    return out


def recs(z, tb, url):
    if url not in z.namelist():
        return []
    return [dict(zip(tb.get(url, []), x)) for x in csv.reader(io.StringIO(z.read(url).decode("utf-8")), delimiter=";")]


s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en"})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE})
assert r.status_code == 201, r.text
A.patch(B + "/api/settings", json={"workspace": f"org:{r.json()['id']}"})
FID, Fr = freelancer(B, A)


def run(S, who):
    def ok(cond, what):
        check(cond, f"{who}: {what}")

    r = S.put(B + OFF_API + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "de", "currency": "EUR", "payment_days": 14,
                                               "company_fields": COMPANY, "invoice_scheme": "RE-{yyyy}-{seq:03}", "credit_scheme": "RK-{yyyy}-{seq:03}"})
    ok(r.ok, "office settings " + r.text[:200])

    def client(**kw):
        r = S.post(B + "/api/clients", json=dict({"street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE"}, **kw))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def invoice(cl, **kw):
        r = S.post(B + D, json={"kind": "invoice", "client_id": cl, "service_from": "2026-10-01", "service_to": "2026-10-20",
                                "items": [{"title": "Schnitt", "qty": 1, "rate": 100, "unit": "piece"}], **kw})
        assert r.status_code == 201, r.text
        return r.json()

    def finalize(did, body=None):
        return S.post(B + f"{D}/{did}/finalize", json=body or {})

    def nxt(kind="invoice"):
        return {x["kind"]: x for x in S.get(B + OFF_API + "/number-ranges").json()["ranges"]}[kind]["next"]

    # ---------------------------------------------------------------- the start number with a reason: 1-672
    r = S.post(B + OFF_API + "/number-ranges/invoice", json={"next": 673, "reason": "Fortsetzung des Altprogramms"})
    ok(r.ok and r.json()["next"] == 673, "the invoice counter continues at 673 " + r.text[:160])

    # ---------------------------------------------------------------- the recipient as the invoice froze it
    c1 = client(name="Kundin Alt GmbH", customer_no="K-100", vat_id="DE123456789")
    i1 = invoice(c1)
    r = finalize(i1["id"])
    ok(r.ok, "invoice 1 finalised " + r.text[:160])
    Y = date.fromisoformat(r.json()["date"]).year
    re_ = lambda n: f"RE-{Y}-{n:03d}"  # noqa: E731
    n1 = r.json()["number"]
    ok(n1 == re_(673), f"invoice 1 has number 673 {n1}")
    ok(S.patch(B + f"/api/clients/{c1}", json={"name": "Kundin Neu AG", "customer_no": "K-999", "street": "Neuer Weg 1"}).ok,
       "the client is renamed after the invoice")
    c2 = client(name="Laufkundschaft Weg KG")
    i2 = invoice(c2)
    n2 = finalize(i2["id"]).json().get("number")
    dbx("UPDATE office_docs SET client_id=NULL WHERE id=?", (i2["id"],))  # the client deleted (client_id ON DELETE SET NULL)
    cr = S.post(B + f"{D}/{i1['id']}/credit").json()
    r = finalize(cr["id"])
    ok(r.ok, "the correction of invoice 1 finalised " + r.text[:160])
    ncr = r.json().get("number")

    # ---------------------------------------------------------------- gaps: a numbered draft, a number set by hand, no reason
    k = nxt()
    d4 = invoice(c1)
    dbx("UPDATE office_docs SET number=? WHERE id=?", (re_(k), d4["id"]))  # a numbered draft from before 2.1289
    i5 = invoice(c1)
    r = finalize(i5["id"], {"number": re_(k + 2), "reason": "Zwei Nummern im Altprogramm vergeben"})
    ok(r.ok and r.json()["number"] == re_(k + 2), "an invoice with a number by hand skips two " + r.text[:160])
    oid = dbx("SELECT org_id FROM office_docs WHERE id=?", (i1["id"],))[0][0]
    dbx("UPDATE office_numbers SET last=last+2 WHERE org_id=? AND kind='invoice' AND period=?", (oid, str(Y)))  # moved without a log line
    last = k + 4

    # ---------------------------------------------------------------- the number ranges page names the gaps
    rg = {x["kind"]: x for x in S.get(B + OFF_API + "/number-ranges").json()["ranges"]}
    g = rg["invoice"].get("gaps") or {}
    ok(g.get("count") == 672 + 2 + 2 and g.get("none") == 2, f"page: 676 missing invoice numbers, 2 without a reason {g}")
    rs = [(x["from"], x["to"], x["code"]) for x in g.get("ranges") or []]
    ok(rs[:4] == [(1, 672, "start"), (k, k, "draft"), (k + 1, k + 1, "manual"), (k + 3, k + 4, "none")],
       f"page: the gaps as ranges, each with its reason {rs}")
    ok("Altprogramms" in (g.get("ranges") or [{}])[0].get("reason", ""), "page: the start number names the logged reason")
    ok(not rg["credit"].get("gaps"), f"page: the corrections have no gap {rg['credit'].get('gaps')}")

    # ---------------------------------------------------------------- the export
    r = S.get(B + OFF_API + f"/gobd/export?from={Y}-01-01&to={Y}-12-31")
    ok(r.ok, f"auditor's export {r.status_code}")
    if not r.ok:
        return
    z = zipfile.ZipFile(io.BytesIO(r.content))
    tb = tables(z)
    inv = {x["Nummer"]: x for x in recs(z, tb, "invoices.csv")}
    a = inv.get(n1) or {}
    ok(a.get("Kunde") == "Kundin Alt GmbH" and a.get("Kundennummer") == "K-100" and a.get("USt_IdNr") == "DE123456789"
       and "Marktstraße 5" in a.get("Anschrift", "") and "Köln" in a.get("Anschrift", "") and a.get("Kundenstamm") == "",
       f"invoices.csv: the renamed client's invoice keeps the frozen recipient {a}")
    ok(a.get("Leistung_von") == "01.10.2026" and a.get("Leistung_bis") == "20.10.2026" and re.fullmatch(r"\d\d\.\d\d\.\d{4}", a.get("Faellig", "")),
       f"invoices.csv: period of service and due day {a}")
    b = inv.get(n2) or {}
    ok(b.get("Kunde") == "Laufkundschaft Weg KG" and "kein Kunde" in b.get("Kundenstamm", ""),
       f"invoices.csv: the invoice of a deleted client keeps its name, Kundenstamm names the missing master {b}")
    c = inv.get(ncr) or {}
    ok(c.get("Storno_von_Nummer") == n1 and c.get("Storno_von") == str(i1["id"]), f"invoices.csv: the correction names the cancelled number {c}")
    pos = recs(z, tb, "positions.csv")
    ok(pos and all(p.get("Steuerschluessel") == "standard" for p in pos), f"positions.csv: the tax key per position {pos[:2]}")
    ok("number_ranges.csv" in tb and "number_ranges.csv" in z.namelist(), "number_ranges.csv is in the ZIP and in index.xml")
    nr = [x for x in recs(z, tb, "number_ranges.csv") if x.get("Reihe") == "invoice" and x.get("Periode") == str(Y)]
    got = [(x["Von"], x["Bis"], x["Grund"]) for x in nr]
    ok(got[:4] == [("1", "672", "Startnummer: Fortsetzung des Altprogramms"), (str(k), str(k), "Entwurf traegt die Nummer"),
                   (str(k + 1), str(k + 1), "Nummer von Hand: Zwei Nummern im Altprogramm vergeben"), (str(k + 3), str(k + 4), "ohne Grund")],
       f"number_ranges.csv: every gap as a range with its reason {got}")
    ok(nr and all(x["Zaehlerstand"] == str(last) and x["Fehlend_gesamt"] == "676" for x in nr), f"number_ranges.csv: counter {last}, 676 missing {nr[:1]}")
    crr = [x for x in recs(z, tb, "number_ranges.csv") if x.get("Reihe") == "credit"]
    ok(crr and crr[0]["Grund"] == "keine Luecke" and crr[0]["Zaehlerstand"] == "1", f"number_ranges.csv: the corrections without a gap {crr}")
    ok(b"Stand beim Export" in z.read("index.xml"), "index.xml: clients.csv is today's master, the frozen recipient in invoices.csv")
    chk = S.get(B + OFF_API + f"/gobd/export?from={Y}-01-01&to={Y}-12-31&check=1").json()
    ok(chk.get("counts", {}).get("number_ranges.csv") == len(recs(z, tb, "number_ranges.csv")), f"the check counts number_ranges.csv {chk.get('counts')}")


run(Fr, "freelancer")
run(A, "organisation")
print(f"p6472_gobd: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
