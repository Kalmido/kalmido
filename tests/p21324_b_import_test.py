#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1324.0 part B: table imports. Own container (start.sh). Invented names only, the files are made here.
 - #6709: an OpenDocument spreadsheet (.ods, recognised by its "mimetype" entry) imports like an .xlsx: every visible sheet a
   sheet of one table (a hidden one not), the header row as titles, kinds from values (currency, percent, date), formulas
   (also into another sheet) taken over, one Kalmido cannot take as its value (counted), list validations (inline and a range
   of a hidden sheet) as select columns, repeated rows rolled out, merged cells merged, the empty repeats LibreOffice writes
   up to row 1 048 576 cost nothing; more than 200 columns: the first 200 and the rest named (#6589)
 - hostile .ods: DOCTYPE / ENTITY, a filled cell repeated 2^31 times in rows and columns, a full row repeated over the cell
   budget, a broken content.xml, a ".ods" without the mimetype: a clean 400, fast; measured in the app container: the peak
   memory of the repeat bombs stays small (they are checked before being rolled out)
 - #6709 (Fable F2): 10 000 list validations on one column of a hidden sheet with 6 000 000 filled rows import in seconds; a hidden
   sheet over the work budget is a clean 400
 - #6589: nothing falls away without a word - an .xlsx with columns beyond the 200 of a sheet imports its first 200 and the
   answer names the columns left out (report cols_left_out + the message); a file within the limit says nothing of it
 - a person without an organisation (freelancer-matrix: sheets)
usage: p21324_b_import_test.py <datadir>      (P21324B_NOSTART=1 = the server already runs)"""
# freelancer-matrix: sheets
import base64
import io
import json
import os
import subprocess
import sys
import time
import zipfile

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import B, CT, check  # noqa: E402

FEAT = FEATURES + ",sheets"
XNS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
RNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def col(i):
    s, i = "", i + 1
    while i:
        i, m = divmod(i - 1, 26)
        s = chr(65 + m) + s
    return s


def xlsx(rows):
    """One sheet "Data" with inline-string / number cells."""
    def cell(r, c, v):
        if isinstance(v, (int, float)):
            return f'<c r="{col(c)}{r}"><v>{v}</v></c>'
        return f'<c r="{col(c)}{r}" t="inlineStr"><is><t>{v}</t></is></c>'
    body = "".join(f'<row r="{r + 1}">' + "".join(cell(r + 1, c, v) for c, v in enumerate(row) if v != "") + "</row>"
                   for r, row in enumerate(rows))
    p = {"[Content_Types].xml": '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
         "xl/workbook.xml": f'<?xml version="1.0"?><workbook {XNS} {RNS}><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>',
         "xl/_rels/workbook.xml.rels": ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                                        'Target="worksheets/sheet1.xml"/></Relationships>'),
         "xl/worksheets/sheet1.xml": f'<?xml version="1.0"?><worksheet {XNS}><sheetData>{body}</sheetData></worksheet>'}
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in p.items():
            z.writestr(k, v)
    return b.getvalue()


# ---------------------------------------------------------------- the .ods maker
ONS = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
       'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"')

def ods(body, styles="", validations="", head="", mime=b"application/vnd.oasis.opendocument.spreadsheet"):
    """body: the <table:table> elements; mimetype first and stored (as LibreOffice writes it)"""
    content = (f'<?xml version="1.0" encoding="UTF-8"?>{head}<office:document-content {ONS}><office:automatic-styles>{styles}'
               f'</office:automatic-styles><office:body><office:spreadsheet>'
               + (f"<table:content-validations>{validations}</table:content-validations>" if validations else "")
               + body + "</office:spreadsheet></office:body></office:document-content>")
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        if mime is not None:
            z.writestr(zipfile.ZipInfo("mimetype"), mime, compress_type=zipfile.ZIP_STORED)
        z.writestr("content.xml", content, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("META-INF/manifest.xml", '<?xml version="1.0"?><manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>',
                   compress_type=zipfile.ZIP_DEFLATED)
    return b.getvalue()

def t(v):
    return f'<table:table-cell office:value-type="string"><text:p>{v}</text:p></table:table-cell>'

def num(v, f=None):
    fa = f' table:formula="{f}"' if f else ""
    return f'<table:table-cell office:value-type="float" office:value="{v}"{fa}><text:p>{v}</text:p></table:table-cell>'

TAIL = '<table:table-cell table:number-columns-repeated="1000"/>'
EMPTY_ROWS = '<table:table-row table:number-rows-repeated="1048000"><table:table-cell table:number-columns-repeated="1024"/></table:table-row>'
BOMB = ('<table:table table:name="B"><table:table-row table:number-rows-repeated="2147483647"><table:table-cell office:value-type="float" '
        'office:value="1" table:number-columns-repeated="2147483647"><text:p>1</text:p></table:table-cell></table:table-row></table:table>')
FULLROWS = ('<table:table table:name="F"><table:table-row table:number-rows-repeated="4000"><table:table-cell office:value-type="float" '
            'office:value="7" table:number-columns-repeated="150"><text:p>7</text:p></table:table-cell></table:table-row></table:table>')


def row(*cells, rep=1):
    ra = f' table:number-rows-repeated="{rep}"' if rep > 1 else ""
    return f"<table:table-row{ra}>" + "".join(cells) + TAIL + "</table:table-row>"


STYLES = ('<style:style style:name="ta1" style:family="table"><style:table-properties table:display="true"/></style:style>'
          '<style:style style:name="ta2" style:family="table"><style:table-properties table:display="false"/></style:style>')
VALID = ('<table:content-validation table:name="val1" table:condition="of:cell-content-is-in-list(&quot;open&quot;;&quot;done&quot;;&quot;later&quot;)" '
         'table:allow-empty-cell="true" table:base-cell-address="Plan.E2"/>'
         '<table:content-validation table:name="val2" table:condition="of:cell-content-is-in-list([$Colours.$A$1:.$A$3])" '
         'table:base-cell-address="Plan.H2"/>')
PLAN = ('<table:table table:name="Plan" table:style-name="ta1">'
        '<table:table-column table:number-columns-repeated="1024"/>'
        + row(t("Item"), t("Price"), t("Qty"), t("Total"), t("State"), t("Share"), t("Day"), t("Colour"))
        + row(t("Gear"), '<table:table-cell office:value-type="currency" office:currency="EUR" office:value="40"><text:p>40,00 €</text:p></table:table-cell>',
              num(3), num(120, "of:=[.B2]*[.C2]"),
              '<table:table-cell table:content-validation-name="val1" office:value-type="string"><text:p>open</text:p></table:table-cell>',
              '<table:table-cell office:value-type="percentage" office:value="0.19"><text:p>19 %</text:p></table:table-cell>',
              '<table:table-cell office:value-type="date" office:date-value="2026-11-17"><text:p>17.11.26</text:p></table:table-cell>',
              '<table:table-cell table:content-validation-name="val2" office:value-type="string"><text:p>green</text:p></table:table-cell>')
        + row(t("Crew"), '<table:table-cell office:value-type="currency" office:currency="EUR" office:value="300"><text:p>300,00 €</text:p></table:table-cell>',
              num(2), num(600, "of:=[.B3]*[$Rates.B2]"),
              '<table:table-cell table:content-validation-name="val1" office:value-type="string"><text:p>done</text:p></table:table-cell>',
              '<table:table-cell office:value-type="percentage" office:value="0.07"><text:p>7 %</text:p></table:table-cell>',
              '<table:table-cell office:value-type="date" office:date-value="2026-12-01T00:00:00"><text:p>01.12.26</text:p></table:table-cell>',
              '<table:table-cell table:content-validation-name="val2" table:number-columns-repeated="1"/>')
        + row(t("Same"), '<table:table-cell office:value-type="currency" office:currency="EUR" office:value="1"><text:p>1,00 €</text:p></table:table-cell>',
              num(1), num(5, "of:=SUM([.B4]~[.C4];3)"), rep=3)
        + row('<table:table-cell table:number-columns-spanned="2" table:number-rows-spanned="1" office:value-type="string"><text:p>Note '
              '<text:span>wide</text:span></text:p></table:table-cell>', '<table:covered-table-cell/>', num(9))
        + EMPTY_ROWS + "</table:table>")
RATES = ('<table:table table:name="Rates" table:style-name="ta1">' + row(t("Name"), t("Value")) + row(t("Factor"), num(2))
         + EMPTY_ROWS + "</table:table>")
COLOURS = ('<table:table table:name="Colours" table:style-name="ta2">' + row(t("red")) + row(t("green")) + row(t("blue"))
           + "</table:table>")
GOOD = ods(PLAN + RATES + COLOURS, STYLES, VALID)


def imp(s, name, data):
    return s.post(B + "/api/sheets/import", data={"space": "private"}, files={"file": (name, data)})


def sheet(s, sid):
    r = s.get(B + f"/api/sheets/{sid}")
    return r.json() if r.ok else {}


kt.fresh(prefix="P21324B")
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
FID, Fr = freelancer(B, A, features=FEAT)


# ================================================================ #6589: the .xlsx import names the columns it leaves out
def wide(s, who):
    rows = [[f"C{i}" for i in range(205)], [i for i in range(205)]]
    rows[1][203] = ""  # column 204 empty in the data, but it has a title: still a column left out
    r = imp(s, "wide.xlsx", xlsx(rows))
    check(r.status_code == 201, f"#6589 {who}: a sheet of 205 columns still imports {r.status_code} {r.text[:200]}")
    if r.status_code != 201:
        return
    rep, msgs = r.json().get("report") or {}, r.json().get("messages") or []
    check(rep.get("columns") == 200 and rep.get("cols_left_out") == 5, f"#6589 {who}: 200 columns in, 5 named as left out {rep}")
    check(any("5 columns left out (at most 200 per sheet)" in m for m in msgs), f"#6589 {who}: the answer says it {msgs}")
    d = sheet(s, r.json()["sheet"]["id"])
    check(len(d.get("columns") or []) == 200 and (d.get("columns") or [{}])[-1].get("title") == "C199",
          f"#6589 {who}: the first 200 columns are there {len(d.get('columns') or [])}")
    r = imp(s, "narrow.xlsx", xlsx([["A", "B"], [1, 2]]))
    rep, msgs = r.json().get("report") or {}, r.json().get("messages") or []
    check(r.status_code == 201 and "cols_left_out" not in rep and not any("left out" in m for m in msgs),
          f"#6589 {who}: a file within the limit says nothing of it {rep} {msgs}")


wide(A, "admin")
wide(Fr, "freelancer")


# ================================================================ #6709: .ods
def at(d, addr):
    return next((c for c in d.get("cells", []) if c["addr"] == addr), {})


def ods_ok(s, who):
    t0 = time.monotonic()
    r = imp(s, "Shoot.ods", GOOD)
    secs = time.monotonic() - t0
    check(r.status_code == 201, f"#6709 {who}: an .ods imports {r.status_code} {r.text[:300]}")
    if r.status_code != 201:
        return
    rep, msgs = r.json().get("report") or {}, r.json().get("messages") or []
    check(secs < 10, f"#6709 {who}: the empty repeats up to row 1 048 576 cost nothing ({secs:.1f} s)")
    check(r.json()["sheet"].get("title") == "Shoot", f"#6709 {who}: the title without .ods {r.json()['sheet'].get('title')}")
    check(rep.get("sheets") == 2 and rep.get("sheets_total") == 2, f"#6709 {who}: two visible sheets, the hidden one not {rep}")
    check(rep.get("rows") == 6 + 1 and rep.get("columns") == 8, f"#6709 {who}: 6 data rows in Plan (one repeated 3 times rolled out) + 1 in Rates, 8 columns {rep}")
    check(rep.get("formulas") == 2 and rep.get("as_value") == 3, f"#6709 {who}: 2 formulas taken over, the union one 3x as value {rep}")
    check(any("2 sheets imported" in m for m in msgs) and any("3 formulas imported as a value" in m for m in msgs), f"#6709 {who}: the answer {msgs}")
    check("cols_left_out" not in rep, f"#6709 {who}: no column left out {rep}")
    d = sheet(s, r.json()["sheet"]["id"])
    check([x["name"] for x in d.get("tabs", [])] == ["Plan", "Rates"], f"#6709 {who}: the sheets with their names {d.get('tabs')}")
    cols = d.get("columns") or []
    check([c["title"] for c in cols] == ["Item", "Price", "Qty", "Total", "State", "Share", "Day", "Colour"], f"#6709 {who}: the titles {[c['title'] for c in cols]}")
    check([c["kind"] for c in cols][:7] == ["text", "currency", "number", "number", "select", "percent", "date"],
          f"#6709 {who}: kinds from values {[c['kind'] for c in cols]}")
    check([o["label"] for o in (cols[4].get("options") if len(cols) > 4 else []) or []] == ["open", "done", "later"],
          f"#6709 {who}: the inline list -> select")
    check([o["label"] for o in (cols[7].get("options") if len(cols) > 7 else []) or []] == ["red", "green", "blue"],
          f"#6709 {who}: the list from a range of the hidden sheet -> select")
    check(at(d, "D1").get("value") == 120 and at(d, "D1").get("raw") == "=B1*C1", f"#6709 {who}: of:=[.B2]*[.C2] taken over {at(d, 'D1')}")
    check(at(d, "D2").get("value") == 600 and "Rates!B1" in (at(d, "D2").get("raw") or ""), f"#6709 {who}: a formula into the other sheet {at(d, 'D2')}")
    check(at(d, "F1").get("value") == 19 or str(at(d, "F1").get("raw")) in ("19", "19 %", "19%"), f"#6709 {who}: 0.19 as 19 % {at(d, 'F1')}")
    check(str(at(d, "G1").get("value") or at(d, "G1").get("raw")).startswith("2026-11-17"), f"#6709 {who}: the date {at(d, 'G1')}")
    check([at(d, f"A{i}").get("raw") for i in (3, 4, 5)] == ["Same"] * 3 and at(d, "D5").get("raw") == "5",
          f"#6709 {who}: a row repeated 3 times, the union formula as its value {[at(d, f'A{i}') for i in (3, 4, 5)]} {at(d, 'D5')}")
    check(at(d, "A6").get("raw") == "Note wide" and (at(d, "A6").get("fmt") or {}).get("merge") == [1, 2] and at(d, "C6").get("value") == 9,
          f"#6709 {who}: the merged cell (and the cell after the covered one) {at(d, 'A6')} {at(d, 'C6')}")
    check(at(d, "E1").get("value") == "open" and at(d, "H1").get("value") == "green", f"#6709 {who}: the select values {at(d, 'E1')} {at(d, 'H1')}")


ods_ok(A, "admin")
ods_ok(Fr, "freelancer")

# more than 200 columns in an .ods (#6589 for ODS too): a filled cell repeated 300 times
r = imp(A, "wide.ods", ods('<table:table table:name="W"><table:table-row><table:table-cell office:value-type="string" table:number-columns-repeated="300">'
                           '<text:p>T</text:p></table:table-cell></table:table-row><table:table-row><table:table-cell office:value-type="float" '
                           'office:value="1" table:number-columns-repeated="300"><text:p>1</text:p></table:table-cell></table:table-row></table:table>'))
rep = r.json().get("report") or {} if r.ok else {}
check(r.status_code == 201 and rep.get("columns") == 200 and rep.get("cols_left_out") == 100
      and any("100 columns left out (at most 200 per sheet)" in m for m in r.json().get("messages") or []),
      f"#6589/#6709 .ods with 300 columns: 200 in, 100 named {r.status_code} {r.text[:300]}")

# an .xlsx is still an .xlsx (it starts with PK as well), also named .ods
r = imp(A, "renamed.ods", xlsx([["A", "B"], [1, 2]]))
check(r.status_code == 201, f"#6709 an .xlsx named .ods still reads as .xlsx {r.status_code} {r.text[:200]}")


# ---------------------------------------------------------------- hostile files: a clean 400, fast
def refused(name, data, want, what):
    t0 = time.monotonic()
    r = imp(A, name, data)
    secs = time.monotonic() - t0
    check(r.status_code == 400 and want in r.text and secs < 10, f"#6709 {what}: 400 '{want}' in {secs:.1f} s - {r.status_code} {r.text[:200]}")


refused("ent.ods", ods(RATES, head='<!DOCTYPE x [<!ENTITY a "aaaaaaaaaa">]>'), "not a spreadsheet file (.ods)", "DOCTYPE / ENTITY")
refused("ent2.ods", ods(RATES.replace("Factor", "Factor<!ENTITY b 'x'>")), "not a spreadsheet file (.ods)", "an ENTITY inside the part")
refused("bomb.ods", ods(BOMB), "Too many rows", "a filled cell repeated 2^31 times in rows and columns")
refused("full.ods", ods(FULLROWS), "Too many filled cells", "a full row repeated over the cell budget")
refused("broken.ods", ods("<table:table table:name='X'><table:table-row>"), "not a spreadsheet file (.ods)", "a broken content.xml")
refused("nomime.ods", ods(RATES, mime=None), "not a spreadsheet file", "an .ods without its mimetype entry")
refused("deep.ods", ods("<table:table table:name='D'>" + "<table:table-row-group>" * 80 + "</table:table-row-group>" * 80 + "</table:table>"),
        "not a spreadsheet file (.ods)", "nesting deeper than 64")

# 2.1324.0 (#6709, Fable F2): 10 000 list validations on the same column of a hidden sheet whose 20 000 filled rows are each
# repeated 300 times (was 10 000 x 201 steps per row, hours): one capture per column and row, only within the range -> imported fast
MANYVAL = "".join(f'<table:content-validation table:name="v{i}" table:condition="of:cell-content-is-in-list([$Hid.$A$1:.$A$2])" '
                  f'table:base-cell-address="V.A2"/>' for i in range(10_000))
HID = ('<table:table table:name="Hid" table:style-name="ta2">' + row(t("x1")) + row(t("x2"))
       + "".join(f'<table:table-row table:number-rows-repeated="300">{t("z")}</table:table-row>' for _ in range(20_000)) + "</table:table>")
VIS = '<table:table table:name="V" table:style-name="ta1">' + row(t("Pick")) + row(t("x1").replace("<table:table-cell ", '<table:table-cell table:content-validation-name="v0" ')) + "</table:table>"
t0 = time.monotonic()
try:
    r = A.post(B + "/api/sheets/import", data={"space": "private"}, files={"file": ("manyval.ods", ods(VIS + HID, STYLES, MANYVAL))}, timeout=60)
    secs, code, body = time.monotonic() - t0, r.status_code, r.text
except Exception as e:  # noqa: BLE001 - the old reader: no answer within a minute
    secs, code, body, r = time.monotonic() - t0, 0, repr(e), None
check(code == 201 and secs < 10, f"#6709 F2: 10 000 validations on one column + 6 000 000 hidden rows: imported in {secs:.1f} s - {code} {body[:200]}")
if code == 201:
    cols = sheet(A, r.json()["sheet"]["id"]).get("columns") or [{}]
    check(cols[0].get("kind") == "select" and [o["label"] for o in cols[0].get("options") or []] == ["x1", "x2"],
          f"#6709 F2: the list still comes from the hidden range {cols[0]}")
# a sheet not taken (hidden) has a work budget too: a filled cell repeated over all columns and a million rows -> a clean 400
refused("hidbomb.ods", ods(RATES + '<table:table table:name="H" table:style-name="ta2"><table:table-row table:number-rows-repeated="1048576">'
                           '<table:table-cell office:value-type="float" office:value="1" table:number-columns-repeated="16384"><text:p>1</text:p>'
                           '</table:table-cell></table:table-row></table:table>', STYLES), "The file is too large", "a hidden sheet over the work budget")

# 2.1324.0 (#6709, review F1 of the second reader): rows of an empty cell 200 wide and a filled one 16 184 wide (the columns left out)
# looped 16 184 times per row outside the work budget -> now a known block costs nothing again: imported fast, all named
WIDECUT = ('<table:table table:name="W" table:style-name="ta1">' + row(t("a")) + "".join(
    '<table:table-row><table:table-cell table:number-columns-repeated="200"/><table:table-cell office:value-type="float" '
    'office:value="1" table:number-columns-repeated="16184"><text:p>1</text:p></table:table-cell></table:table-row>' for _ in range(100_000))
    + "</table:table>")
t0 = time.monotonic()
try:
    r = A.post(B + "/api/sheets/import", data={"space": "private"}, files={"file": ("widecut.ods", ods(WIDECUT, STYLES))}, timeout=60)
    secs, code, body = time.monotonic() - t0, r.status_code, r.text
except Exception as e:  # noqa: BLE001 - the old reader: no answer within a minute
    secs, code, body, r = time.monotonic() - t0, 0, repr(e), None
check(code == 201 and secs < 10 and (r.json().get("report") or {}).get("cols_left_out") == 16184,
      f"#6709 review F1: 100 000 rows filled only past column 200: imported in {secs:.1f} s, 16 184 columns named - {code} {body[:300]}")

# ---------------------------------------------------------------- in the app container: the memory the repeat bombs take
EMPTY = ods('<table:table table:name="E"><table:table-row><table:table-cell office:value-type="string"><text:p>x</text:p></table:table-cell>'
            '</table:table-row>' + EMPTY_ROWS * 50 + '</table:table>')
FILES = {k: base64.b64encode(v).decode() for k, v in (("bomb", ods(BOMB)), ("full", ods(FULLROWS)), ("empty", EMPTY))}
PROBE = "FILES = " + json.dumps(FILES) + r'''
import base64, json, time, tracemalloc
from kalmido.core.config import app
from kalmido.core.errors import BadInput
from kalmido.sheets.odsread import shx_read_ods_all
out = {}
def measure(key, raw):
    tracemalloc.start()
    t0 = time.monotonic()
    try:
        g = shx_read_ods_all(raw, 30)
        err = None
        out[key + "_rows"] = sum(len(x.rows) for x in g)
    except BadInput as e:
        err = e.text() if hasattr(e, "text") else str(e)
    out[key] = [err, tracemalloc.get_traced_memory()[1], time.monotonic() - t0]
    tracemalloc.stop()
with app.test_request_context("/", headers={"Accept-Language": "en"}):
    for key, b64 in FILES.items():
        measure(key, base64.b64decode(b64))
print(json.dumps(out))
'''
r = subprocess.run(["docker", "exec", "-i", CT, "python", "-"], input=PROBE, capture_output=True, text=True, timeout=300)
check(r.returncode == 0, "the probe runs in the app container " + r.stderr[-800:])
P = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {}
MB = 1024 * 1024
print("measured:", json.dumps(P))
for key, want in (("bomb", "Too many rows"), ("full", "Too many filled cells")):
    v = P.get(key) or ["", 1e12, 99]
    check(want in (v[0] or "") and v[1] < 16 * MB and v[2] < 5, f"#6709 {key}: refused before rolling out, peak {v[1] / MB:.1f} MB, {v[2]:.2f} s")
v = P.get("empty") or ["?", 1e12, 99]
check(v[0] is None and P.get("empty_rows") == 1 and v[1] < 16 * MB and v[2] < 5,
      f"#6709 50 x 1 048 000 empty repeated rows: one row read, peak {v[1] / MB:.1f} MB, {v[2]:.2f} s {v[0]}")

sys.exit(kt.done("p21324_b_import"))
