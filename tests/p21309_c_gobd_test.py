#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1309.0 part C API test (#6471, #6467 (4)): the export for the tax auditor is complete.
Invented people, firms and figures only (example.com).
freelancer-matrix: office
All of it in a personal office (a person without an organisation, its own admin; tests/freelancer_fixture.py):
 - belege/ carries the stored PDF and e-invoice XML of a finalised invoice byte for byte: the bytes in the ZIP are the ones
   the app serves, their SHA-256 stands in invoices.csv and equals pdf_sha256 / xml_sha256 of the document
 - receipts.csv names the file of a receipt in belege/ with its SHA-256; a receipt of the period in the trash stays in, marked
   Papierkorb (also with its file)
 - dunning.csv: a finalised reminder with the invoice it reminds of and its stored PDF
 - the new tables (bank lines, card statements + lines, vehicles, logbook, its log, entertainment, trips + items, asset
   register, ledger bookings) hold the rows of the period only; a bank line of an import taken back is marked
   zurueckgenommen, a removed drive Papierkorb; an invoice in the trash stays in invoices.csv, marked
 - log.csv carries the values before and after of a change (Vorher / Nachher)
 - chain_check.csv: intakt with the number of links; chain_heads.csv: per chain the last link's hash as in the database;
   after a position of a finalised invoice is changed in the database: gebrochen, the first bad document named
 - index.xml names every table, every CSV line has its columns, the check counts what the ZIP holds
 - another office (a second freelancer's) exports none of it
usage: p21309_c_gobd_test.py <datadir>"""
import csv
import hashlib
import io
import os
import re
import sys
import zipfile
from datetime import timedelta

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
import testclock  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import FAILS, OKS, B, DATA, check, done, fresh, setup, until  # noqa: E402,F401

OFF = "/api/office"
D = OFF + "/docs"
T0 = testclock.today()
TODAY = T0.isoformat()
D30 = (T0 - timedelta(days=30)).isoformat()
D20 = (T0 - timedelta(days=20)).isoformat()
D10 = (T0 - timedelta(days=10)).isoformat()
FROM = (T0 - timedelta(days=60)).isoformat()
OLD = "2000-01-05"  # outside the period
P = f"?from={FROM}&to={TODAY}"
COMPANY = {"name": "Frida Film", "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE", "vat_id": "DE123456789",
           "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}
TS = TODAY + "T09:00:00+00:00"


def sql(q, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(q, args)
        c.commit()
        return r.fetchall() if re.match(r"\s*(SELECT|WITH)\b", q, re.I) else None
    finally:
        c.close()


def new_id(table, cols, vals):
    sql(f"INSERT INTO {table}({', '.join(cols)}) VALUES({', '.join('?' * len(vals))})", vals)
    return sql(f"SELECT MAX(id) FROM {table}")[0][0]  # dbx wraps a SELECT (no INSERT ... RETURNING in a WITH)


def tiny_pdf(text):
    """A one-page PDF with a text layer (hand-written, no library)."""
    stream = f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
    return out


def sha(b):
    return hashlib.sha256(b).hexdigest()


def tables(z):
    """{url: [column names]} of index.xml."""
    x = z.read("index.xml").decode("utf-8")
    out = {}
    for t in re.findall(r"<Table>(.*?)</Table>", x, re.S):
        url = re.search(r"<URL>(.*?)</URL>", t).group(1)
        out[url] = re.findall(r"<Name>(.*?)</Name>", t)[1:]  # the first Name is the table's
    return out


def rows(z, url):
    return list(csv.reader(io.StringIO(z.read(url).decode("utf-8"), newline=""), delimiter=";"))


def recs(z, tb, url):
    return [dict(zip(tb[url], x)) for x in rows(z, url)]


def export(s):
    r = s.get(B + OFF + "/gobd/export" + P)
    assert r.ok, (r.status_code, r.text[:300])
    return zipfile.ZipFile(io.BytesIO(r.content))


fresh()
A = setup()
FID, Fr = freelancer(B, A)  # freelancer-matrix: office (the personal office, its own admin)
assert Fr.put(B + OFF + "/settings", json={"lang": "en", "company_fields": COMPANY}).ok
CL = Fr.post(B + "/api/clients", json={"name": "Beispielkunde AG", "street": "Marktweg 5", "zip": "50667", "city": "Köln", "country": "DE",
                                       "email_invoice": "billing@kunde.example", "payment_terms_days": 14}).json()["id"]


def invoice(title, day):
    r = Fr.post(B + D, json={"kind": "invoice", "client_id": CL, "project_title": title, "date": day, "service_from": day,
                             "items": [{"title": "Schnitt", "qty": 1, "rate": 1000}]})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    r = Fr.post(B + f"{D}/{did}/finalize")
    assert r.ok, r.text
    return did, Fr.get(B + f"{D}/{did}").json()["number"]


I1, N1 = invoice("Imagefilm", D30)
assert Fr.post(B + f"{D}/{I1}/payments", json={"date": D20, "amount": 100, "method": "transfer"}).ok
I4, N4 = invoice("Rechnung im Papierkorb", D20)
OID = sql("SELECT org_id FROM office_docs WHERE id=?", (I1,))[0][0]
sql("UPDATE office_docs SET deleted_at=? WHERE id=?", (TS, I4))  # in the trash (dbx passes the finalising lock)

# a change with before / after in the office log
r = Fr.post(B + D, json={"kind": "invoice", "client_id": CL, "project_title": "Alt-Titel"})
I3 = r.json()["id"]
check(Fr.patch(B + f"{D}/{I3}", json={"project_title": "Neu-Titel"}).ok, "a draft changed (office log: update)")

# a reminder over the overdue invoice
r = Fr.post(B + D + "/reminder", json={"doc_ids": [I1], "level": 1})
check(r.status_code == 201, f"a reminder draft {r.status_code} {r.text[:200]}")
RM = r.json().get("id") if r.status_code == 201 else None
r = Fr.post(B + f"{D}/{RM}/finalize") if RM else None
check(r is not None and r.ok, f"the reminder finalised {r.status_code if r is not None else ''} {r.text[:200] if r is not None else ''}")

# receipts: one live, one in the trash
UWS = Fr.get(B + OFF + "/books").json()["upload_ws"]
PDF1, PDF2 = tiny_pdf("Beleg Eins"), tiny_pdf("Beleg Papierkorb")


def receipt(name, data, day):
    r = Fr.post(B + "/api/docs", data={"ws": UWS}, files={"files": (name + ".pdf", data, "application/pdf")})
    assert r.ok, r.text
    nid = r.json()["ids"][0]
    until(lambda: (lambda x: x.ok and x.json()["state"] in ("done", "failed"))(Fr.get(B + f"/api/docs/{nid}")), 90)
    assert Fr.patch(B + f"/api/docs/{nid}", json={"amount": "119.00", "date": day, "name": name}).ok
    assert Fr.put(B + f"/api/docs/{nid}/receipt", json={"category": "Software", "vat_pct": "19", "keep": True}).ok
    return nid


R1, R2 = receipt("Beleg Eins", PDF1, D10), receipt("Beleg Papierkorb", PDF2, D10)
sql("UPDATE fs_nodes SET deleted_at=? WHERE id=?", (TS, R2))

# the tables of the retention export: rows inside and outside the period
IMP_U = new_id("office_bank_imports", ("org_id", "filename", "fmt", "created_at", "undone_at"), (OID, "auszug.csv", "csv", TS, TS))
TX1 = new_id("office_bank_tx", ("org_id", "day", "amount", "currency", "counterpart", "purpose", "hash", "created_at"),
             (OID, D10, "-49.90", "EUR", "Beispiel Telekom", "Rechnung Mobilfunk", "h1", TS))
TXU = new_id("office_bank_tx", ("org_id", "import_id", "day", "amount", "currency", "counterpart", "purpose", "hash", "created_at"),
             (OID, IMP_U, D10, "200.00", "EUR", "Beispielkunde AG", "Zahlung zurueckgenommen", "h2", TS))
TXO = new_id("office_bank_tx", ("org_id", "day", "amount", "currency", "counterpart", "purpose", "hash", "created_at"),
             (OID, OLD, "-1.00", "EUR", "Alt", "Vor dem Zeitraum", "h3", TS))
VH = new_id("office_vehicles", ("org_id", "name", "plate", "created_at", "updated_at"), (OID, "Kombi", "M-XY 123", TS, TS))
DR1 = new_id("office_drives", ("org_id", "vehicle_id", "day", "start_place", "dest", "purpose", "km", "created_at", "updated_at"),
             (OID, VH, D10, "Musterstadt", "Köln", "Dreh", "42.5", TS, TS))
DRX = new_id("office_drives", ("org_id", "vehicle_id", "day", "start_place", "dest", "purpose", "km", "created_at", "updated_at", "deleted_at"),
             (OID, VH, D10, "Musterstadt", "Bonn", "Entfernt", "10", TS, TS, TS))
DRO = new_id("office_drives", ("org_id", "vehicle_id", "day", "start_place", "dest", "purpose", "km", "created_at", "updated_at"),
             (OID, VH, OLD, "Musterstadt", "Alt", "Alt", "5", TS, TS))
ML = new_id("office_meals", ("org_id", "date", "place_name", "occasion", "tip", "created_at", "updated_at"),
            (OID, D10, "Gasthaus Beispiel", "Projektbesprechung", "5.00", TS, TS))
TR = new_id("office_trips", ("org_id", "date_from", "date_to", "dest", "created_at", "updated_at"), (OID, D20, D20, "Hamburg", TS, TS))
TI = new_id("office_trip_items", ("org_id", "trip_id", "date", "category", "amount", "created_at", "updated_at"), (OID, TR, D20, "taxi", "18.00", TS, TS))
EQ = new_id("office_equipment", ("org_id", "name", "purchase_date", "purchase_net", "life_months", "created_at", "updated_at"),
            (OID, "Kamera Beispiel", D30, "2500.00", 36, TS, TS))
EQX = new_id("office_equipment", ("org_id", "name", "created_at", "updated_at"), (OID, "Stativ (Verleih, kein Kaufdatum)", TS, TS))
LE = new_id("office_ledger_entries", ("org_id", "year", "kind", "day", "debit", "credit", "amount", "text", "created_at", "updated_at"),
            (OID, T0.year, "manual", D10, "4900", "1200", "12.34", "Umbuchung Beispiel", TS, TS))
CC = new_id("office_cc_cards", ("org_id", "holder_name", "last4", "created_at"), (OID, "Frida", "4242", TS))
CS = new_id("office_cc_statements", ("org_id", "card_id", "month", "day", "total", "created_at"), (OID, CC, D10[:7], D10, "30.00", TS))
CLN = new_id("office_cc_lines", ("org_id", "statement_id", "day", "merchant", "amount"), (OID, CS, D10, "Beispiel Software", "30.00"))

# ---------------------------------------------------------------- the check and the ZIP
r = Fr.get(B + OFF + "/gobd/export" + P + "&check=1")
ch = r.json().get("counts", {}) if r.ok else {}
NEW = ("bank_tx.csv", "card_statements.csv", "card_lines.csv", "vehicles.csv", "logbook.csv", "logbook_log.csv", "meals.csv", "meal_files.csv",
       "trips.csv", "trip_items.csv", "assets.csv", "ledger_entries.csv", "dunning.csv", "chain_check.csv", "chain_heads.csv")
check(r.ok and all(u in ch for u in NEW), f"check: the new tables are counted {r.status_code} {sorted(ch)}")
z = export(Fr)
tb = tables(z)
names = set(z.namelist())
check(all(u in names for u in tb) and all(u in tb for u in NEW), f"index.xml names every table, each in the ZIP {sorted(tb)}")
bad = [(u, i) for u in tb for i, x in enumerate(rows(z, u)) if len(x) != len(tb[u])]
check(not bad, f"every CSV line has the columns of index.xml {bad[:5]}")
got = {u: len(rows(z, u)) for u in tb}
check(got == {u: ch.get(u) for u in tb}, f"the check counts what the ZIP holds {got} {ch}")
x = z.read("index.xml").decode("utf-8")
check("<Accuracy>1</Accuracy>" in x and "<DecimalSymbol>,</DecimalSymbol>" in x and "belege/" in x, "index.xml: own accuracy for km, decimal comma, belege named")

# belege: the invoice's PDF + XML byte for byte
inv = {v["Nummer"]: v for v in recs(z, tb, "invoices.csv")}
i1 = inv.get(N1, {})
db1 = sql("SELECT pdf_sha256, xml_sha256 FROM office_docs WHERE id=?", (I1,))[0]
pdf = Fr.get(B + f"{D}/{I1}/pdf").content
xml = Fr.get(B + f"{D}/{I1}/xml").content
pn, xn = i1.get("PDF_Dateiname", ""), i1.get("XML_Dateiname", "")
check(pn.startswith("belege/rechnungen/") and pn in names and z.read(pn) == pdf and sha(z.read(pn)) == i1.get("PDF_SHA-256") == db1[0],
      f"invoices.csv: the stored PDF in belege/, byte for byte, its SHA-256 = pdf_sha256 {pn} {i1.get('PDF_SHA-256')} {db1[0]}")
check(xn.endswith(".xml") and xn in names and z.read(xn) == xml and sha(z.read(xn)) == i1.get("XML_SHA-256") == db1[1],
      f"invoices.csv: the e-invoice XML in belege/ with its SHA-256 = xml_sha256 {xn}")
check(i1.get("Kennzeichen") == "" and inv.get(N4, {}).get("Kennzeichen") == "Papierkorb",
      f"invoices.csv: the invoice in the trash stays, marked {inv.get(N4)}")
check("hinweise.txt" not in names, f"no file note when every file matches {z.read('hinweise.txt')[:300] if 'hinweise.txt' in names else ''}")

# receipts: file + SHA-256, the one in the trash marked
rc = {v["Beleg_ID"]: v for v in recs(z, tb, "receipts.csv")}
r1, r2 = rc.get(str(R1), {}), rc.get(str(R2), {})
check(r1.get("Dateiname", "") in names and r1.get("Dateiname", "").startswith("belege/eingang/") and z.read(r1["Dateiname"]) == PDF1
      and r1.get("SHA-256") == sha(PDF1) and r1.get("Kennzeichen") == "", f"receipts.csv: the receipt's file in belege/ with its SHA-256 {r1}")
check(r2.get("Kennzeichen") == "Papierkorb" and r2.get("SHA-256") == sha(PDF2), f"receipts.csv: the receipt in the trash stays, marked {r2}")

# reminders
dn = recs(z, tb, "dunning.csv")
check(len(dn) == 1 and dn[0]["Rechnungen"] == N1 and dn[0]["PDF_Dateiname"] in names and sha(z.read(dn[0]["PDF_Dateiname"])) == dn[0]["PDF_SHA-256"],
      f"dunning.csv: the reminder, its invoice and its PDF {dn}")

# the new tables: the period, the marks
bt = {v["id"]: v for v in recs(z, tb, "bank_tx.csv")}
check(set(bt) == {str(TX1), str(TXU)} and bt[str(TX1)]["amount"] == "-49,90" and bt[str(TX1)]["day"] == ".".join(reversed(D10.split("-")))
      and bt[str(TX1)]["Kennzeichen"] == "" and bt[str(TXU)]["Kennzeichen"] == "zurueckgenommen",
      f"bank_tx.csv: the period only, decimal comma, an undone import marked {bt}")
lb = {v["id"]: v for v in recs(z, tb, "logbook.csv")}
check(set(lb) == {str(DR1), str(DRX)} and lb[str(DRX)]["Kennzeichen"] == "Papierkorb" and lb[str(DR1)]["km"] == "42,5",
      f"logbook.csv: the drives of the period, a removed one marked {lb}")
check([v["name"] for v in recs(z, tb, "vehicles.csv")] == ["Kombi"], "vehicles.csv: the vehicle")
check([v["id"] for v in recs(z, tb, "meals.csv")] == [str(ML)] and recs(z, tb, "meals.csv")[0]["tip"] == "5,00", "meals.csv: the entertainment receipt")
check([v["id"] for v in recs(z, tb, "trips.csv")] == [str(TR)] and [v["id"] for v in recs(z, tb, "trip_items.csv")] == [str(TI)], "trips + trip_items")
check([v["id"] for v in recs(z, tb, "assets.csv")] == [str(EQ)] and recs(z, tb, "assets.csv")[0]["purchase_net"] == "2500,00",
      "assets.csv: the asset with its purchase, not the rental item without a purchase day")
check([v["id"] for v in recs(z, tb, "ledger_entries.csv")] == [str(LE)] and recs(z, tb, "ledger_entries.csv")[0]["amount"] == "12,34", "ledger_entries.csv")
check([v["id"] for v in recs(z, tb, "card_statements.csv")] == [str(CS)] and [v["id"] for v in recs(z, tb, "card_lines.csv")] == [str(CLN)],
      "card statements + lines")

# log with before / after
lg = [v for v in recs(z, tb, "log.csv") if v["Aktion"] == "update" and v["Dokument_ID"] == str(I3)]
check(lg and "Alt-Titel" in lg[0]["Vorher"] and "Neu-Titel" in lg[0]["Nachher"], f"log.csv: the values before and after {lg}")

# the hash chain
cc = recs(z, tb, "chain_check.csv")
n_links = sql("SELECT COUNT(*) FROM office_docs WHERE org_id=? AND chain_seq IS NOT NULL", (OID,))[0][0]
check(len(cc) == 1 and cc[0]["Ergebnis"] == "intakt" and cc[0]["Glieder"] == str(n_links) and n_links >= 3, f"chain_check.csv: intact {cc} {n_links}")
heads = {x[0]: x[1] for x in sql("SELECT DISTINCT ON (chain_key) chain_key, chain_hash FROM office_docs WHERE org_id=? AND chain_seq IS NOT NULL "
                                 "ORDER BY chain_key, chain_seq DESC", (OID,))}
hd = {v["Reihe"]: v["Hash"] for v in recs(z, tb, "chain_heads.csv")}
check(hd == heads and len(hd) >= 1, f"chain_heads.csv: each chain's last link {hd} {heads}")
check(all(v.get("Kanon_Version") in ("1", "2") for v in recs(z, tb, "chain_heads.csv")), "chain_heads.csv: the canonical version of each head")

# ---------------------------------------------------------------- 2.1309.0 (#6471): a bill the virus scanner locked stays out, named
MF = new_id("office_meal_files", ("org_id", "meal_id", "name", "file", "size", "mime", "sha256", "created_at"),
            (OID, ML, "bewirtung.pdf", "gesperrt-beispiel.pdf", 10, "application/pdf", "", TS))
sql("INSERT INTO upload_scan(kind, ref_id, ver, org_id, state, sig, created_at) VALUES('omf',?,0,?,'infected','Test-Signatur',?)", (MF, OID, TS))
z = export(Fr)
tb = tables(z)
mf = {v["id"]: v for v in recs(z, tb, "meal_files.csv")}
hw = z.read("hinweise.txt").decode("utf-8") if "hinweise.txt" in z.namelist() else ""
check(str(MF) in mf and not mf[str(MF)].get("Dateiname") and not any(n.startswith("belege/bewirtung/") for n in z.namelist())
      and f"Bewirtung {ML}" in hw, f"meal_files.csv: a locked bill is not exported, hinweise.txt names it {mf.get(str(MF))} {hw[:300]}")
sql("DELETE FROM upload_scan WHERE kind='omf' AND ref_id=?", (MF,))
sql("DELETE FROM office_meal_files WHERE id=?", (MF,))

# ---------------------------------------------------------------- another office exports none of it
_FID2, Fi = freelancer(B, A, "fiona")
za = export(Fi)
ta = tables(za)
check(not any(N1 in "".join(x) for x in rows(za, "invoices.csv")) and not rows(za, "bank_tx.csv") and not rows(za, "logbook.csv")
      and not rows(za, "dunning.csv") and not any(n.startswith("belege/") for n in za.namelist()) and set(ta) >= set(NEW),
      "another office: nothing of the freelancer's in its export")

# ---------------------------------------------------------------- a changed position breaks the chain
sql("UPDATE office_doc_items SET title='Manipuliert' WHERE doc_id=?", (I1,))
z = export(Fr)
tb = tables(z)
cc = recs(z, tb, "chain_check.csv")
check(cc and cc[0]["Ergebnis"] == "gebrochen" and cc[0]["Erster_Fehler_ID"] == str(I1) and cc[0]["Grund"] == "data",
      f"chain_check.csv: broken, the first bad document named {cc}")

sys.exit(done("p21309_c_gobd"))
