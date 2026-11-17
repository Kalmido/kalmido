#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1315.0 B (#6590) office imports, own container (server key + org encryption on). Invented companies, people, accounts
and figures only.
tenant-matrix: office  freelancer-matrix: office
 - (a) a real number cell of a spreadsheet is read as stored (dot = decimal), never by the text rule: 29.125 in a number
   cell of the fixed-cost import is 29.13 (was 29125), a text cell "1.500" stays 1500; the readers of old documents
   (legacyimport _num) read 0.125 of a number cell as 0.125 (was 125)
 - (b) the same day of the bank first as CSV, then as CAMT: the CAMT preview names every booking "already there"
   (dup + dup_other), the import adds none; a booking of the CAMT with another counterpart and purpose on the same day
   and amount is new; the same format still keeps two equal bookings apart (fingerprint, not this check)
 - (c) one imported old document goes into the office trash (DELETE /api/office/legacy/archive/<id>): also after it was
   edited (the run's undo refuses then); gone from the list, the dialog and the PDF, listed in the office trash; its number
   is free (a corrected PDF takes it); the restore refuses while the number is used again (409) and brings the number back
   once it is free; a document of a locked month stays (409); an old invoice in the trash is kept by law (delete for good
   409), a quotation goes; another office / the other person: 404 and nothing changes
 - (d) a bank CSV in another currency (a currency column or "12,50 USD" in the amount cell) is refused per row, never booked
   as the office's currency; a CAMT batch booking gives every position with its own amount, counterpart and purpose (was the
   first only) and the same file again finds them all; positions that do not add up stay one row with every text; the DATEV
   check names the reason of every row (also beyond the 20 shown); the fixed-cost import starts in the current year (was
   2026); an overlapping booking batch of the archive (later the whole year after a half year) leaves out the lines there
 - the person without an organisation (tests/freelancer_fixture.py) in the personal office: the same for (a) to (d)
usage: p21315_b_importe_test.py <datadir>"""
import base64
import io
import os
import subprocess
import zipfile
from datetime import timedelta
from xml.sax.saxutils import escape

import kt
from kt import B, CT, check
from freelancer_fixture import freelancer
import testclock

KEY = base64.b64encode(os.urandom(32)).decode()
kt.fresh(env={"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ORGCRYPT_DELAY": "0", "KALMIDO_SECRET_KEY": KEY}, prefix="P21315B")

A = kt.setup()
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True, "modules": ["comments"]})
FEAT = "cal,comments,collab,office,clients,files,docs"
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A, "fiona", features=FEAT)  # freelancer-matrix: office (the personal office, its own admin)
Fr.patch(B + "/api/settings", json={"workspace": "private"})
O = "/api/office"
K = O + "/bank"
TODAY = testclock.today()
DAY = [(TODAY - timedelta(days=n)).isoformat() for n in range(0, 40)]
WHO = (("org", A), ("freelancer", Fr))
REF = [0]


def in_app(code):
    """Python inside the server container (the app loaded, c = a connection, system context) -> stdout + stderr."""
    body = "\n".join("    " + x for x in code.split("\n"))
    out = subprocess.run(["docker", "exec", CT, "python", "-c",
                          "import app\nfrom kalmido.core.db import connect\nfrom kalmido.core.pg import system_ctx\nc = connect()\n"
                          "with system_ctx(c):\n" + body + "\nc.close()"], capture_output=True, text=True)
    return out.stdout + out.stderr


def xlsx(rows):
    """A minimal .xlsx: numbers (int / float) as number cells, everything else as inline text cells."""
    def cell(ref, v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return f'<c r="{ref}"><v>{v!r}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'
    data = "".join(f'<row r="{i + 1}">' + "".join(cell(f"{chr(65 + j)}{i + 1}", v) for j, v in enumerate(r) if v != "") + "</row>"
                   for i, r in enumerate(rows))
    ns = "http://schemas.openxmlformats.org"
    parts = {
        "[Content_Types].xml": f'<?xml version="1.0"?><Types xmlns="{ns}/package/2006/content-types"/>',
        "xl/workbook.xml": f'<?xml version="1.0"?><workbook xmlns="{ns}/spreadsheetml/2006/main" xmlns:r="{ns}/officeDocument/2006/relationships">'
                           '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<?xml version="1.0"?><Relationships xmlns="{ns}/package/2006/relationships"><Relationship Id="rId1" '
                                      f'Type="{ns}/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<?xml version="1.0"?><worksheet xmlns="{ns}/spreadsheetml/2006/main"><sheetData>{data}</sheetData></worksheet>',
    }
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in parts.items():
            z.writestr(n, d)
    return b.getvalue()


def camt(rows, iban=None):
    """A CAMT.053 statement: rows (signed amount, day, name, purpose); no references (a bank that sends none)."""
    out = []
    for amt, day, name, purpose in rows:
        who = "Dbtr" if amt > 0 else "Cdtr"
        out.append(f'<Ntry><Amt Ccy="EUR">{abs(amt):.2f}</Amt><CdtDbtInd>{"CRDT" if amt > 0 else "DBIT"}</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>'
                   f"<BookgDt><Dt>{day}</Dt></BookgDt><NtryDtls><TxDtls><RltdPties><{who}><Pty><Nm>{name}</Nm></Pty></{who}>"
                   f"</RltdPties><RmtInf><Ustrd>{purpose}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>")
    REF[0] += 1
    acct = f"<Acct><Id><IBAN>{iban}</IBAN></Id></Acct>" if iban else ""
    return ('<?xml version="1.0" encoding="UTF-8"?><Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt><Stmt>'
            f'<Id>S{REF[0]}</Id>{acct}{"".join(out)}</Stmt></BkToCstmrStmt></Document>')


def de(day):
    return f"{day[8:10]}.{day[5:7]}.{day[:4]}"


CSV_MAP = {"date": 0, "amount": 1, "counterpart": 2, "title": 3, "decimal": ",", "date_format": "DD.MM.YYYY"}


# ======================================================================== (a) number cells of a spreadsheet
for who, s in WHO:
    p = f"(a) {who}: "
    raw = xlsx([["Name", "Amount (net)", "Due month"], ["Cloud storage", 29.125, 0], ["Office rent", "1.500", 0], ["Tea", 0.5, 0]])
    r = s.post(B + O + "/fixed-costs/import/preview", files={"file": ("kosten.xlsx", raw, "application/octet-stream")})
    check(r.ok, p + f"fixed-cost preview {r.status_code} {r.text[:300]}")
    got = {x["label"]: x["amount"] for x in (r.json().get("rows") or [])} if r.ok else {}
    check(got.get("Cloud storage") == "29.13", p + f"29.125 of a number cell is 29.13 (was 29125.00) {got}")
    check(got.get("Office rent") == "1500.00", p + f"the text cell '1.500' keeps the text rule (1500) {got}")
    check(got.get("Tea") == "0.50", p + f"0.5 of a number cell {got}")

out = in_app("from kalmido.office.legacyimport import fi_xlsx_read, _num\nfrom kalmido.core.csvimport import amount_text\n"
             "import base64\n"
             f"g = fi_xlsx_read(base64.b64decode({base64.b64encode(xlsx([['Rate', 'Text'], [0.125, '0.125'], [12.345, '12.345']])).decode()!r}))['sheet1']\n"
             "print('CELL', _num(g[1][0]), _num(g[2][0]), amount_text(g[1][1]), amount_text(g[2][1]))")
cells = next((x.split()[1:] for x in out.splitlines() if x.startswith("CELL ")), [])
check(cells[:2] == ["0.125", "12.345"], f"(a) old documents: number cells 0.125 / 12.345 read as stored (were 125 / 12345) {cells} {out[-300:]}")
check(cells[2:] == ["125", "12345"], f"(a) text cells keep the German-first text rule {cells}")

# ======================================================================== (b) duplicates across formats
for who, s in WHO:
    p = f"(b) {who}: "
    d1, d2 = DAY[3], DAY[4]
    text = ("Datum;Betrag;Name;Verwendungszweck\n"
            f"{de(d1)};-49,90;Stadtwerke Musterstadt;Abschlag Strom Kunde 4711\n"
            f"{de(d1)};1.200,00;Beispiel GmbH;Rechnung R-2026-017\n"
            f"{de(d2)};-12,00;Kiosk am Platz;Kartenzahlung\n")
    r = s.post(B + K + "/import", json={"text": text, "filename": "konto.csv", "mapping": CSV_MAP})
    check(r.status_code == 201 and r.json().get("count") == 3, p + f"CSV import {r.status_code} {r.text[:300]}")
    # the same day from the bank as CAMT: other spelling of the names, the purpose cut differently
    st = camt([(-49.90, d1, "STADTWERKE MUSTERSTADT", "Abschlag Strom Kunde 4711"),
               (1200.00, d1, "Beispiel GmbH Musterstadt", "Rechnung R-2026-017"),
               (-12.00, d2, "Kiosk am Platz", "Kartenzahlung girocard 0815"),
               (-49.90, d1, "Gasversorgung Nord", "Abschlag Gas")])  # same day and amount, another booking
    r = s.post(B + K + "/import/preview", json={"text": st, "filename": "auszug.xml"})
    j = r.json() if r.ok else {}
    rows = {x["purpose"]: x for x in j.get("rows") or []}
    check(r.ok and j.get("count") == 1 and j.get("dup_count") == 3, p + f"CAMT preview after the CSV: 3 already there, 1 new {r.status_code} {r.text[:400]}")
    check(all(rows.get(k, {}).get("dup") for k in ("Abschlag Strom Kunde 4711", "Rechnung R-2026-017", "Kartenzahlung girocard 0815")),
          p + f"the preview names all three already there {rows}")
    # the equal texts found it by the fingerprint already; another counterpart / a longer purpose only by this check
    check(all(rows.get(k, {}).get("dup_other") for k in ("Rechnung R-2026-017", "Kartenzahlung girocard 0815")),
          p + f"the preview says they came from a statement in another format {rows}")
    check(not rows.get("Abschlag Gas", {}).get("dup"), p + f"another booking of the same day and amount stays new {rows.get('Abschlag Gas')}")
    r = s.post(B + K + "/import", json={"text": st, "filename": "auszug.xml"})
    check(r.status_code == 201 and r.json().get("count") == 1 and r.json().get("dup_count") == 3, p + f"CAMT import adds only the new one {r.text[:300]}")
    items = s.get(B + K + "/tx?state=all").json()["items"]
    check(len([t for t in items if t["day"] == d1 and t["amount"] == "-49.90"]) == 2 and len(items) == 4,
          p + f"no doubles in the bookings ({len(items)}) {[(t['day'], t['amount'], t['purpose']) for t in items]}")
    # the same format keeps the fingerprint's rule: a second CSV with two equal rows -> the one already there and one new
    text2 = ("Datum;Betrag;Name;Verwendungszweck\n"
             f"{de(d2)};-12,00;Kiosk am Platz;Kartenzahlung\n"
             f"{de(d2)};-12,00;Kiosk am Platz;Kartenzahlung\n")
    r = s.post(B + K + "/import/preview", json={"text": text2, "filename": "konto2.csv", "mapping": CSV_MAP})
    j = r.json() if r.ok else {}
    check(r.ok and j.get("count") == 1 and j.get("dup_count") == 1, p + f"CSV again with two equal rows: one there, one new {r.text[:300]}")

# ======================================================================== (c) one old document into the trash
def tiny_pdf(text):
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


def arch_up(s, rid, number, text, day, kind="invoice"):
    r = s.post(B + O + "/legacy/archive", data={"run_id": rid, "kind": kind, "number": number, "client_name": "Altkunde",
                                                "date": day, "amount": "100.00"},
               files={"file": (f"{number}.pdf", tiny_pdf(text), "application/pdf")})
    check(r.status_code == 201, f"(c) upload {number} {r.status_code} {r.text[:200]}")
    return r.json().get("id", 0) if r.status_code == 201 else 0


def arch_ids(s):
    return {x["id"]: x["number"] for x in s.get(B + O + "/legacy/archive").json().get("items") or []}


ARCH = "/api/office/legacy/archive"  # the whole path (tests/freelancer_coverage_test.py finds the calls)
for who, s, other in (("org", A, Fr), ("freelancer", Fr, A)):
    p = f"(c) {who}: "
    rid = s.post(B + O + "/legacy/archive/run").json()["run_id"]
    a1 = arch_up(s, rid, f"ALT-{who}-1", f"Rechnung 1 {who}", DAY[10])
    a2 = arch_up(s, rid, f"ALT-{who}-2", f"Rechnung 2 {who}", DAY[11])
    a3 = arch_up(s, rid, f"ANG-{who}-3", f"Angebot 3 {who}", DAY[12], kind="offer")
    r = other.delete(B + f"/api/office/legacy/archive/{a1}")
    check(r.status_code == 404 and a1 in arch_ids(s), p + f"another office cannot put it into the trash {r.status_code}")
    # edited: the run's undo refuses, the single document still goes
    check(s.patch(B + ARCH + f"/{a2}", json={"paid": 1}).ok, p + "an old invoice marked paid")
    check(s.post(B + O + f"/legacy/runs/{rid}/undo").status_code == 409, p + "the run's undo refuses after the edit (unchanged)")
    r = s.delete(B + ARCH + f"/{a2}")
    check(r.ok, p + f"the edited old invoice goes into the trash {r.status_code} {r.text[:200]}")
    r = s.delete(B + ARCH + f"/{a1}")
    check(r.ok, p + f"an old invoice goes into the trash {r.status_code} {r.text[:200]}")
    ids = arch_ids(s)
    check(a1 not in ids and a2 not in ids and a3 in ids, p + f"gone from the archive list {ids}")
    check(s.get(B + ARCH + f"/{a1}").status_code == 404 and s.get(B + ARCH + f"/{a1}/pdf").status_code == 404,
          p + "the dialog and the PDF answer 404")
    tr_ = s.get(B + O + "/trash").json().get("items") or []
    check(any(x.get("core") == "oarchive" and x["id"] == a1 and f"ALT-{who}-1" in x.get("label", "") for x in tr_),
          p + f"listed in the office trash with its number {[(x.get('core'), x['id'], x.get('label')) for x in tr_]}")
    check(s.delete(B + ARCH + f"/{a1}").status_code == 404, p + "a second delete: 404")
    r = other.post(B + f"/api/office/legacy/archive/{a1}/restore")
    check(r.status_code == 404 and a1 not in arch_ids(s), p + f"another office cannot restore it {r.status_code}")
    # the number is free: a corrected PDF takes it; the restore waits until it is free again
    a4 = arch_up(s, rid, f"ALT-{who}-1", f"Rechnung 1 korrigiert {who}", DAY[10])
    r = s.post(B + ARCH + f"/{a1}/restore")
    check(r.status_code == 409 and f"ALT-{who}-1" in r.text, p + f"the restore refuses while the number is used again {r.status_code} {r.text[:200]}")
    check(a1 not in arch_ids(s), p + "the refused restore leaves it in the trash")
    check(s.delete(B + ARCH + f"/{a4}").ok, p + "the corrected one into the trash")
    r = s.post(B + ARCH + f"/{a1}/restore")
    check(r.ok and r.json().get("number") == f"ALT-{who}-1" and arch_ids(s).get(a1) == f"ALT-{who}-1",
          p + f"restored with its number {r.status_code} {r.text[:200]}")
    check(s.get(B + ARCH + f"/{a1}/pdf").status_code == 200, p + "its PDF opens again")
    # the trash: an old invoice is kept by law, a quotation goes for good
    r = s.delete(B + f"/api/office/trash/core/oarchive/{a2}")
    check(r.status_code == 409, p + f"an old invoice in the trash is kept by law {r.status_code} {r.text[:200]}")
    check(s.delete(B + ARCH + f"/{a3}").ok, p + "a quotation into the trash")
    r = s.delete(B + f"/api/office/trash/core/oarchive/{a3}")
    check(r.ok, p + f"a quotation is deleted for good from the trash {r.status_code} {r.text[:200]}")
    # a locked month binds it
    a5 = arch_up(s, rid, f"ALT-{who}-5", f"Rechnung 5 {who}", "2025-03-10")
    r = s.post(B + O + "/periods/lock", json={"through": "2025-03", "confirm": "03/2025"})
    check(r.ok, p + f"March 2025 locked {r.status_code} {r.text[:200]}")
    r = s.delete(B + ARCH + f"/{a5}")
    check(r.status_code == 409 and a5 in arch_ids(s), p + f"a document of a locked month stays {r.status_code} {r.text[:200]}")

# ======================================================================== (d) the smaller points
def camt_batch(day, total, positions, ref):
    """One CAMT entry of total (signed) with positions [(signed amount or None, name, purpose)] and the bank's reference."""
    side = "Dbtr" if total > 0 else "Cdtr"
    txs = []
    for a, n, pu in positions:
        amt = "" if a is None else f'<Amt Ccy="EUR">{abs(a):.2f}</Amt><CdtDbtInd>{"CRDT" if a > 0 else "DBIT"}</CdtDbtInd>'
        txs.append(f"<TxDtls>{amt}<RltdPties><{side}><Pty><Nm>{n}</Nm></Pty></{side}></RltdPties><RmtInf><Ustrd>{pu}</Ustrd></RmtInf></TxDtls>")
    REF[0] += 1
    return ('<?xml version="1.0" encoding="UTF-8"?><Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt><Stmt>'
            f'<Id>S{REF[0]}</Id><Ntry><Amt Ccy="EUR">{abs(total):.2f}</Amt><CdtDbtInd>{"CRDT" if total > 0 else "DBIT"}</CdtDbtInd>'
            f"<Sts><Cd>BOOK</Cd></Sts><BookgDt><Dt>{day}</Dt></BookgDt><AcctSvcrRef>{ref}</AcctSvcrRef>"
            f"<NtryDtls>{''.join(txs)}</NtryDtls></Ntry></Stmt></BkToCstmrStmt></Document>")


def q(v):
    return '"' + str(v).replace('"', '""') + '"' if v != "" else ""


def head(cat, name, ver, fy, frm="", to=""):
    f = ['"EXTF"', "700", str(cat), f'"{name}"', str(ver), "20260101120000000", "", '"RE"', '""', '""', "1234567", "12345", fy, "4", frm, to]
    return ";".join(f + [""] * (31 - len(f)))


COLS16 = ("Konto", "Name (Adressatentyp Unternehmen)", "Ort")
COLS21 = ("Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz", "Kurs", "Konto", "Gegenkonto (ohne BU-Schlüssel)",
          "BU-Schlüssel", "Belegdatum", "Belegfeld 1", "Belegfeld 2", "Buchungstext")


def extf16(rows):
    lines = [head(16, "Debitoren/Kreditoren", 5, "20260101"), ";".join(q(c) for c in COLS16)]
    lines += [";".join(q(x) for x in r) for r in rows]
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def extf21(year, rows):
    lines = [head(21, "Buchungsstapel", 13, f"{year}0101", f"{year}0101", f"{year}1231"), ";".join(q(c) for c in COLS21)]
    for a, sh, k, g, d, b1, t in rows:
        lines.append(";".join([a, q(sh), q("EUR"), "", k, g, "", d, q(b1), "", q(t)]))
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


ARCH_YEAR = TODAY.year - 3
HALF = [("100,00", "S", "1200", "8400", f"{m:02d}01", f"RE-{m}", f"Honorar {m}") for m in range(1, 7)]
FULL = HALF + [("100,00", "S", "1200", "8400", f"{m:02d}01", f"RE-{m}", f"Honorar {m}") for m in range(7, 13)]

for who, s in WHO:
    p = f"(d) {who}: "
    check(s.put(B + O + "/settings", json={"datev_extf": {"advisor_no": "1234567", "client_no": "12345", "fy_start": 1, "acct_len": 4,
                                                        "chart": "SKR03"}}).ok, p + "DATEV settings")
    # -- a bank CSV in another currency
    d1 = DAY[20]
    text = ("Datum;Betrag;Währung;Name;Verwendungszweck\n"
            f"{de(d1)};-10,00;EUR;Laden Eins;Einkauf Euro\n"
            f"{de(d1)};-20,00;USD;Shop Two;Purchase Dollar\n")
    m = {"date": 0, "amount": 1, "counterpart": 3, "title": 4, "decimal": ",", "date_format": "DD.MM.YYYY"}
    r = s.post(B + K + "/import/preview", json={"text": text, "filename": "fx.csv", "mapping": m})
    rows = {x["purpose"]: x for x in (r.json().get("rows") or [])} if r.ok else {}
    check(r.ok and rows.get("Purchase Dollar", {}).get("error") and rows.get("Purchase Dollar", {}).get("currency") == "USD"
          and not rows.get("Einkauf Euro", {}).get("error"), p + f"a USD row of a currency column is refused (was booked as EUR) {rows}")
    text = "Datum;Betrag;Name;Verwendungszweck\n" + f"{de(d1)};-30,00 USD;Shop Three;Purchase in the cell\n{de(d1)};-5,00 EUR;Laden Zwei;Euro in der Zelle\n"
    r = s.post(B + K + "/import", json={"text": text, "filename": "fx2.csv", "mapping": CSV_MAP})
    j = r.json() if r.status_code == 201 else {}
    check(r.status_code == 201 and j.get("count") == 1 and j.get("skipped") == 1, p + f"'30,00 USD' in the amount cell is refused, the EUR row booked {r.text[:300]}")
    # -- a CAMT batch booking
    d2 = DAY[21]
    st = camt_batch(d2, -150.00, [(-50.00, "Lieferant Eins", "RG 1"), (-60.00, "Lieferant Zwei", "RG 2"), (-40.00, "Lieferant Drei", "RG 3")], f"SAMMEL-{who}")
    r = s.post(B + K + "/import/preview", json={"text": st, "filename": "sammel.xml"})
    rows = sorted(((x["counterpart"], x["amount"], x["purpose"]) for x in (r.json().get("rows") or [])), key=str) if r.ok else []
    check(rows == [("Lieferant Drei", "-40.00", "RG 3"), ("Lieferant Eins", "-50.00", "RG 1"), ("Lieferant Zwei", "-60.00", "RG 2")],
          p + f"every position of the batch booking with its amount (was the first only, with the total) {rows} {r.text[:200]}")
    r = s.post(B + K + "/import", json={"text": st, "filename": "sammel.xml"})
    check(r.status_code == 201 and r.json().get("count") == 3, p + f"three bookings {r.text[:200]}")
    r = s.post(B + K + "/import/preview", json={"text": st, "filename": "sammel.xml"})
    check(r.ok and r.json().get("count") == 0 and r.json().get("dup_count") == 3, p + f"the same file again: all three there {r.text[:300]}")
    st2 = camt_batch(DAY[22], -99.00, [(None, "Firma A", "Teil A"), (None, "Firma B", "Teil B")], f"SAMMEL2-{who}")
    r = s.post(B + K + "/import/preview", json={"text": st2, "filename": "sammel2.xml"})
    rows = r.json().get("rows") or [] if r.ok else []
    check(len(rows) == 1 and rows[0]["amount"] == "-99.00" and "Teil A" in rows[0]["purpose"] and "Teil B" in rows[0]["purpose"],
          p + f"positions without amounts stay one row with every text {rows}")
    # -- the DATEV check names every row's reason
    rws = [(f"{70100 + i}", f"Lieferant {i}", "Halle") for i in range(22)] + [(f"{70200 + i}", "", "Jena") for i in range(3)]
    r = s.post(B + O + "/datev/import/check", files={"file": ("extf.csv", extf16(rws), "text/csv")})
    j = r.json() if r.ok else {}
    late = [x for x in j.get("reasons") or [] if x["row"] > 22]
    check(r.ok and len(j.get("rows") or []) == 20 and len(late) == 3 and all(x["reason"] for x in late),
          p + f"the reasons of rows 25 to 27 are named (only 20 rows shown) {r.status_code} {j.get('reasons')} {r.text[:200]}")
    # -- the fixed-cost import starts in the current year
    r = s.post(B + O + "/fixed-costs/import/preview", files={"file": ("k.xlsx", xlsx([["Name", "Amount (net)", "Due month"], ["Hosting", 12, 0], ["Insurance", 240, 3]]), "application/octet-stream")})
    st_ = {x["label"]: x["start"] for x in (r.json().get("rows") or [])} if r.ok else {}
    check(st_.get("Hosting") == f"{TODAY.year}-01-01" and st_.get("Insurance") == f"{TODAY.year}-03-01",
          p + f"the costs start in {TODAY.year} (was fixed 2026) {st_}")
    # -- overlapping batches of the booking archive
    r = s.post(B + O + "/books/archive/import", files=[("file", (f"EXTF_Buchungsstapel_{ARCH_YEAR}_H1.csv", extf21(ARCH_YEAR, HALF), "application/octet-stream"))])
    check(r.status_code == 201, p + f"archive: the half year {r.status_code} {r.text[:200]}")
    r = s.post(B + O + "/books/archive/check", files=[("file", (f"EXTF_Buchungsstapel_{ARCH_YEAR}.csv", extf21(ARCH_YEAR, FULL), "application/octet-stream"))])
    j = r.json() if r.ok else {}
    ys = {y["year"]: y for y in j.get("years") or []}
    check(r.ok and ys.get(ARCH_YEAR, {}).get("bookings") == 6 and any("6" in (f.get("reason") or "") for f in j.get("files") or []),
          p + f"archive: the whole year after the half year adds only the 6 new lines and says why {ys} {j.get('files')}")
    r = s.post(B + O + "/books/archive/import", files=[("file", (f"EXTF_Buchungsstapel_{ARCH_YEAR}.csv", extf21(ARCH_YEAR, FULL), "application/octet-stream"))])
    check(r.status_code == 201, p + f"archive: the whole year {r.status_code} {r.text[:200]}")
    r = s.post(B + O + "/books/archive/check", files=[("file", (f"EXTF_Buchungsstapel_{ARCH_YEAR}_H1.csv", extf21(ARCH_YEAR, HALF[:3]), "application/octet-stream"))])
    j = r.json() if r.ok else {}
    check(r.ok and not j.get("years") and any(f.get("kind") == "duplicate" for f in j.get("files") or []),
          p + f"archive: a batch whose every line is there already is a duplicate {j.get('files')} {j.get('years')}")

raise SystemExit(kt.done("p21315_b_importe"))
