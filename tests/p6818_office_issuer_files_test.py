#!/usr/bin/env python3
# kalmido-suite: fresh
"""API tests (#6818): an invoice issuer's key fetches the finished file of its own documents (office/issdocs.py isd_file).
Own container (start.sh, mode workspaces, KALMIDO_ISSUER_KEYS on). Invented companies, people and figures only.
tenant-matrix: office  freelancer-matrix: office
 - GET /api/v1/issuer/docs/{id}/file?kind=pdf|xml: the archived file byte for byte (the bytes the office's own download
   serves), X-Content-SHA256 = its SHA-256 = office_docs.pdf_sha256 / xml_sha256
 - kind=xml of a ZUGFeRD invoice = the XML embedded in its PDF; of an XRechnung = the stored invoice XML
 - a draft: 409 not_final; no archived file (removed from the disk): 409 not_final, never rendered anew
 - another issuer's document, a person's document and another area's: 404; a correction a person made of the issuer's
   invoice (it inherits issuer_id): 409 while a draft, the file once finalised
 - kind missing / unknown, an unknown query field: 400
 - a clock of its own: 10 a minute per issuer, the 11th 429 rate_limited (another issuer is not held up)
 - every delivery one line of the office log (issuer_read, target file:<kind>:<id>), two downloads two lines
 - the personal office of a person without an organisation (Frida): her key fetches her finalised invoice
 - ISS_REUSED names office.pdfweb.epdf_stored
usage: p6818_office_issuer_files_test.py <datadir>"""
import base64
import hashlib
import os
import re
import subprocess
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check  # noqa: E402
import dbx as dbxm  # noqa: E402
from freelancer_fixture import FEATURES, PASSWORD, freelancer  # noqa: E402

kt.docker_logs_on_first_fail()
DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
OF = "/api/office"
D = OF + "/docs"
V = B + "/api/v1"
CR = "/issuer/clients/by-ref/"
TODAY = __import__("datetime").date.today()
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "phone": "+49 40 1234567", "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001"}
ADDR = {"street": "Marktweg 5", "zip": "50667", "city": "Köln", "country": "DE"}


def sql(q, args=(), write=False):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(q, args)
        if write:
            c.commit()
            return None
        return r.fetchall()
    finally:
        c.close()


def hk(key):
    return {"Authorization": "Bearer " + key}


def kput(key, ref, b):
    return requests.put(V + CR + ref, headers=hk(key), json=b, timeout=30)


def kpost(key, b):
    return requests.post(V + "/issuer/invoices", headers=hk(key), json=b, timeout=30)


def kfile(key, did, kind="pdf", extra=""):
    q = f"?kind={kind}" if kind is not None else "?"
    return requests.get(V + f"/issuer/docs/{did}/file{q}{extra}", headers=hk(key), timeout=30)


def code(r):
    try:
        e = r.json().get("error")
        return e.get("code") if isinstance(e, dict) else None
    except ValueError:
        return None


def setup_area(S, code_):
    assert S.put(B + OF + "/settings", json={"lang": "de", "company_fields": COMPANY}).ok
    r = S.post(B + OF + "/num-ranges", json={"code": code_, "scheme": code_ + "-{yyyy}-{seq:03}"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def issuer(S, rg, name):
    r = S.post(B + OF + "/issuers", json={"name": name, "range_id": rg, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()["issuer"]["id"], r.json()["key"]


def body(ref, ext="acc:1"):
    return {"client_ref": ref, "client": {"external_ref": ext}, "service_from": TODAY.isoformat(), "service_to": TODAY.isoformat(),
            "items": [{"text": "Tarif Studio, Dezember", "qty": 1, "unit": "flat", "rate": "150.00", "tax": "standard"}],
            "expect": {"net": "150.00", "tax": "28.50", "gross": "178.50"}}


def finalise(S, did):
    hold = S.get(B + D + f"/{did}/number-preview").json().get("client_hold") or {}
    r = S.post(B + D + f"/{did}/finalize", json={"client_hold_ok": hold.get("at")} if hold else {})
    assert r.ok, f"finalise {did}: {r.status_code} {r.text[:300]}"


def embedded_xml(pdf):
    """The e-invoice XML inside a PDF, read by the office's own reader (office/einvoice_in.py ei_from_pdf) in the container."""
    code_ = ("import base64, sys, app\nfrom kalmido.office.einvoice_in import ei_from_pdf\n"
             "x = ei_from_pdf(base64.b64decode(sys.stdin.read()))\nprint(base64.b64encode(x or b'').decode())")
    r = subprocess.run(["docker", "exec", "-i", kt.CT, "python", "-c", code_], input=base64.b64encode(pdf).decode(),
                       capture_output=True, text=True, timeout=120)
    try:
        return base64.b64decode((r.stdout or "").strip().splitlines()[-1])
    except (IndexError, ValueError):
        print("embedded_xml failed:", r.stderr[-1500:], flush=True)
        return b""


def log_lines(iid, target):
    return sql("SELECT COUNT(*) FROM office_doc_log WHERE issuer_id=? AND action='issuer_read' AND target=?", (iid, target))[0][0]


# ---------------------------------------------------------------- the container
kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ISSUER_KEYS": "1", "TASKS_WATCHDOG_INTERVAL": "3600"}, data=DATA)
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
assert A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"}).ok
FID, Fr = freelancer(B, A)
Fr.patch(B + "/api/settings", json={"workspace": "private"})

RG = setup_area(A, "GT")
IID, KEY = issuer(A, RG, "Shop")
IID2, KEY2 = issuer(A, RG, "Booking")
IID3, KEY3 = issuer(A, RG, "Clock")  # its own key for the clock (10 files a minute each)
FRG = setup_area(Fr, "WEB")
FI, FK = issuer(Fr, FRG, "Own script")
for k, ref, extra in ((KEY, "acc:1", {}), (KEY, "acc:xr", {"buyer_reference": "991-12345-67"}), (KEY3, "acc:1", {}), (FK, "acc:1", {})):
    assert kput(k, ref, {"name": f"Kundin {ref}", **ADDR, "email_invoice": "rechnung@kunde.example", **extra}).status_code == 201

# ---------------------------------------------------------------- a draft: 409 not_final
DR = kpost(KEY, body("draft:1")).json()["doc_id"]
r = kfile(KEY, DR)
check(r.status_code == 409 and code(r) == "not_final", f"a draft: 409 not_final {r.status_code} {r.text[:200]}")
r = kfile(KEY, DR, "xml")
check(r.status_code == 409 and code(r) == "not_final", f"a draft's XML: 409 not_final {r.status_code}")

# ---------------------------------------------------------------- ZUGFeRD: the stored PDF byte for byte, the XML inside it
ZF = kpost(KEY, body("fin:1")).json()["doc_id"]
finalise(A, ZF)
pdf_sha, xml_sha = sql("SELECT pdf_sha256, xml_sha256 FROM office_docs WHERE id=?", (ZF,))[0]
r = kfile(KEY, ZF)
own = A.get(B + D + f"/{ZF}/pdf")
check(r.status_code == 200 and r.headers.get("Content-Type", "").startswith("application/pdf") and r.content == own.content,
      f"kind=pdf: the archived PDF, the same bytes as the office's own download {r.status_code} {len(r.content)} {len(own.content)}")
check(r.headers.get("X-Content-SHA256") == hashlib.sha256(r.content).hexdigest() == pdf_sha,
      f"the header X-Content-SHA256 = the SHA-256 of the bytes = the one noted at finalising {r.headers.get('X-Content-SHA256')} {pdf_sha}")
ZPDF = r.content
r = kfile(KEY, ZF, "xml")
check(r.status_code == 200 and r.headers.get("Content-Type", "").startswith("application/xml") and r.content.lstrip().startswith(b"<?xml")
      and r.headers.get("X-Content-SHA256") == hashlib.sha256(r.content).hexdigest() == xml_sha,
      f"kind=xml: the stored XML with its SHA-256 {r.status_code} {r.headers.get('X-Content-SHA256')} {xml_sha}")
check(b"urn:xeinkauf.de:kosit:xrechnung" not in r.content and r.content == embedded_xml(ZPDF), "ZUGFeRD: kind=xml is exactly the XML embedded in the PDF")
check(log_lines(IID, f"file:pdf:{ZF}") == 1 and log_lines(IID, f"file:xml:{ZF}") == 1, "each download one line of the office log")
check(kfile(KEY, ZF).status_code == 200 and log_lines(IID, f"file:pdf:{ZF}") == 2, "a second download: a second line (never merged)")

# ---------------------------------------------------------------- XRechnung: the original XML
XR = kpost(KEY, body("fin:xr", ext="acc:xr")).json()["doc_id"]
cur = A.get(B + D + f"/{XR}").json()
r = A.patch(B + D + f"/{XR}", json={"einvoice_format": "xrechnung", "expect_updated_at": cur.get("updated_at")})
check(r.ok, f"setup: a person makes the draft an XRechnung {r.status_code} {r.text[:200]}")
finalise(A, XR)
r = kfile(KEY, XR, "xml")
check(r.status_code == 200 and b"urn:xeinkauf.de:kosit:xrechnung" in r.content and r.content == A.get(B + D + f"/{XR}/xml").content
      and r.headers.get("X-Content-SHA256") == sql("SELECT xml_sha256 FROM office_docs WHERE id=?", (XR,))[0][0],
      f"XRechnung: kind=xml is the stored invoice XML byte for byte {r.status_code} {r.text[:200]}")

# ---------------------------------------------------------------- a person's correction inherits issuer_id
r = A.post(B + D + f"/{ZF}/credit", json={})
CRD = r.json().get("id") if r.ok else 0
check(r.ok and sql("SELECT issuer_id FROM office_docs WHERE id=?", (CRD,))[0][0] == IID, f"setup: a person's correction inherits issuer_id {r.status_code}")
r = kfile(KEY, CRD)
check(r.status_code == 409 and code(r) == "not_final", f"the correction while a draft: 409 not_final {r.status_code}")
finalise(A, CRD)
r = kfile(KEY, CRD)
check(r.status_code == 200 and r.headers.get("X-Content-SHA256") == sql("SELECT pdf_sha256 FROM office_docs WHERE id=?", (CRD,))[0][0],
      f"the finalised correction: its archived file {r.status_code} {r.text[:200] if r.status_code != 200 else ''}")

# ---------------------------------------------------------------- not its own: 404
r = kfile(KEY2, ZF)
check(r.status_code == 404, f"another issuer of the same office: 404 {r.status_code}")
PD = A.post(B + D, json={"kind": "invoice", "client_id": sql("SELECT client_id FROM office_docs WHERE id=?", (ZF,))[0][0],
                         "items": [{"title": "Beratung", "qty": 1, "rate": 100}]}).json().get("id")
check(PD and kfile(KEY, PD).status_code == 404, "a person's own document: 404")

# ---------------------------------------------------------------- wrong input: 400
check(kfile(KEY, ZF, None).status_code == 400 and kfile(KEY, ZF, "zip").status_code == 400, "kind missing or unknown: 400")
check(kfile(KEY, ZF, "pdf", "&inline=1").status_code == 400, "an unknown query field: 400")

# ---------------------------------------------------------------- the archived file has gone: 409, never rendered anew
XF = kpost(KEY, body("fin:gone")).json()["doc_id"]
finalise(A, XF)
LS = ("import glob, sys, app\nfrom kalmido.core.config import OFFICE_DIR\n"
      "print(len(glob.glob(f'{OFFICE_DIR}/*/doc{sys.argv[1]}-*.pdf')))")
RM = "import glob, os, sys, app\nfrom kalmido.core.config import OFFICE_DIR\n[os.remove(p) for p in glob.glob(f'{OFFICE_DIR}/*/doc{sys.argv[1]}-*.pdf')]"


def in_ct(code_, arg):
    return subprocess.run(["docker", "exec", kt.CT, "python", "-c", code_, str(arg)], capture_output=True, text=True, timeout=120).stdout.strip()


check(in_ct(LS, XF).endswith("1"), "setup: the archived PDF is on the disk")
in_ct(RM, XF)
r = kfile(KEY, XF)
check(r.status_code == 409 and code(r) == "not_final" and not r.content.startswith(b"%PDF"),
      f"the archived file gone: 409 not_final, no new rendering {r.status_code} {r.text[:200]}")
check(in_ct(LS, XF).endswith("0"), "nothing was written anew")
check(sql("SELECT 1 FROM office_doc_log WHERE doc_id=? AND action='store_missing'", (XF,)), "the office log names the missing file")

# ---------------------------------------------------------------- the clock: 10 a minute per issuer
CD = kpost(KEY3, body("clock:1")).json()["doc_id"]
finalise(A, CD)
codes = [kfile(KEY3, CD).status_code for _ in range(11)]
r = kfile(KEY3, CD)
check(codes[:10] == [200] * 10 and codes[10] == 429 and r.status_code == 429 and code(r) == "rate_limited" and r.headers.get("Retry-After"),
      f"10 files a minute, then 429 rate_limited {codes} {r.status_code}")
check(log_lines(IID3, f"file:pdf:{CD}") == 10, "the refused downloads write no line")
check(kfile(KEY2, ZF).status_code == 404, "another issuer is not held up by that clock (its own answer, here 404)")

# ---------------------------------------------------------------- the personal office (freelancer-matrix: office)
FD = kpost(FK, body("f:1")).json()["doc_id"]
finalise(Fr, FD)
r = kfile(FK, FD)
check(r.status_code == 200 and r.content == Fr.get(B + D + f"/{FD}/pdf").content, f"Frida's key: the archived PDF of her finalised invoice {r.status_code}")
# tenant: GET /api/v1/issuer/docs/{}/file
r = kfile(FK, ZF)
check(r.status_code == 404, f"another area's document: 404 {r.status_code}")
check(kfile(KEY, FD).status_code == 404, "the organisation's key never reaches Frida's document: 404")

# ---------------------------------------------------------------- ISS_REUSED
src = open(os.path.join(N, "..", "kalmido", "office", "issuers.py"), encoding="utf-8").read()
m = re.search(r"ISS_REUSED = \(([^)]*)\)", src)
check(m and "office.pdfweb.epdf_stored" in re.findall(r'"([^"]+)"', m.group(1)), "ISS_REUSED names the archive this suite reads with the issuer")

sys.exit(kt.done("p6818_office_issuer_files"))
