#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1324.0 part B: table imports. Own container (start.sh). Invented names only, the files are made here.
 - #6589: nothing falls away without a word - an .xlsx with columns beyond the 200 of a sheet imports its first 200 and the
   answer names the columns left out (report cols_left_out + the message); a file within the limit says nothing of it
 - a person without an organisation (freelancer-matrix: sheets)
usage: p21324_b_import_test.py <datadir>      (P21324B_NOSTART=1 = the server already runs)"""
# freelancer-matrix: sheets
import io
import os
import sys
import zipfile

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import B, check  # noqa: E402

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

sys.exit(kt.done("p21324_b_import"))
