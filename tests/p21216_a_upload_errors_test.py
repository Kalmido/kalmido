#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1216.0 (#6109): the document upload names its reasons (freelancer-matrix: files)
 - POST /api/docs where nothing could be stored (only refused files): 400 WITH an `error` text - the reasons themselves
   (the app shows them instead of "Error 400"), the list `errors` as before (backwards compatible: ids, errors, dups)
 - several refused files: all reasons in the one error text
 - one stored + one refused: 201 as before, the refused one in `errors`, no `error` (the answer is no failure)
 - the same as a person without an organisation (tests/freelancer_fixture.py)
usage: p21216_a_upload_errors_test.py <datadir>      (KMT_NOSTART=1 / P21216_NOSTART=1: a running server)"""
import sys

from freelancer_fixture import FEATURES, freelancer
from kt import B, check, done, fresh, setup


def tiny_pdf(text):
    """A one-page PDF with a text layer (as tests/p21148_receipts_test.py)."""
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


fresh(prefix="P21216")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEATURES})
FID, Fr = freelancer(B, A, features=FEATURES)


def up(s, files):
    return s.post(B + "/api/docs", data={"ws": "private"}, files=[("files", (n, d, "application/pdf")) for n, d in files])


for who, s in (("alice", A), ("frida (no organisation)", Fr)):
    r = up(s, [("leer.pdf", b"")])
    j = r.json()
    check(r.status_code == 400 and "leer.pdf" in (j.get("error") or "") and "empty" in j["error"], f"{who}: only an empty file -> 400 with the reason as error ({r.status_code} {j.get('error')!r})")
    check(j.get("ids") == [] and j.get("dups") == [] and len(j.get("errors") or []) == 1, f"{who}: ids / errors / dups as before ({j})")
    r = up(s, [("a-leer.pdf", b""), ("b-leer.pdf", b"")])
    j = r.json()
    check(r.status_code == 400 and "a-leer.pdf" in (j.get("error") or "") and "b-leer.pdf" in j["error"] and len(j["errors"]) == 2, f"{who}: two refused files -> both reasons in the one error ({j.get('error')!r})")
    r = up(s, [("gut-" + who[:5] + ".pdf", tiny_pdf("Rechnung " + who[:5])), ("c-leer.pdf", b"")])
    j = r.json()
    check(r.status_code == 201 and len(j.get("ids") or []) == 1 and len(j.get("errors") or []) == 1 and "error" not in j, f"{who}: one stored + one refused -> 201, the refusal in errors only ({r.status_code} {j})")

sys.exit(done("p21216_a_upload_errors_test"))
