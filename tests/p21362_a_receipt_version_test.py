#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1362.0 (#6327): the receipt's assignment (PUT /api/docs/{id}/receipt) carries a version, so the bookkeeping's receipt
sheet never puts back what another device changed meanwhile
(freelancer-matrix: files)
 - GET /api/docs/{id}/receipt: receipt.updated_at = the version of the assignment ('' while it is no receipt)
 - PUT with expect_updated_at: only the fields sent change (project, category, VAT rate and "a receipt" stay as they are);
   another version -> 409 with the current state under "receipt", nothing written; '' while it became a receipt meanwhile ->
   409 too; '' on a document that is no receipt -> written
 - PUT without expect_updated_at: the old behaviour (missing project / category = none; agents and older clients)
 - the document's own part (PATCH /api/docs/{id}, amount and date) answers 409 against its edited_at as before (#4770)
 - a person without an organisation (the fixture): everything in her private workspace
usage: p21362_a_receipt_version_test.py <datadir>      (KMT_NOSTART=1 / P21362A_NOSTART=1: a running server)"""
import os
import sys

from freelancer_fixture import FEATURES, freelancer, login
from kt import B, check, done, fresh, setup

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")


def dbw(sql, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


def tiny_pdf(text):
    """A one-page PDF with a text layer (as tests/p2110_b_api_test.py)."""
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


fresh(prefix="P21362A")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEATURES})
FID, Fr = freelancer(B, A, features=FEATURES)
Fr2 = login(B, "frida")  # the same person on a second device
Fr2.patch(B + "/api/settings", json={"lang": "en"})


def upload(name):
    r = Fr.post(B + "/api/docs", data={"ws": "private"}, files={"files": (name, tiny_pdf("Beleg " + name), "application/pdf")})
    assert r.status_code == 201, r.text
    return r.json()["ids"][0]


def rc(s, nid):
    r = s.get(B + f"/api/docs/{nid}/receipt")
    assert r.ok, r.text
    return r.json()["receipt"]


def older(nid):
    """The version the other device reads lies in an earlier second (versions are whole seconds): set_at an hour back."""
    dbw("UPDATE rc_receipts SET set_at = set_at - interval '1 hour' WHERE node_id=?", (nid,))


# freelancer-matrix: files
r = Fr.post(B + "/api/lists", json={"name": "Werbefilm Beispiel", "kind": "project"})
check(r.ok, f"setup: a project {r.status_code} {r.text[:200]}")
P = r.json()["id"]
D = upload("rechnung.pdf")
check(rc(Fr, D)["updated_at"] == "" and not rc(Fr, D)["is_receipt"], "#6327: no receipt yet: version ''")

# a document that is no receipt becomes one with the version ''
r = Fr.put(B + f"/api/docs/{D}/receipt", json={"category": "Office", "vat_pct": "19", "project_id": P, "keep": True, "expect_updated_at": ""})
check(r.status_code == 200, f"#6327: '' on a document without receipt -> written {r.status_code} {r.text[:200]}")
V0 = r.json()["receipt"]["updated_at"]
check(bool(V0) and r.json()["receipt"]["category"] == "Office", "#6327: the answer carries the new version")
r = Fr2.put(B + f"/api/docs/{D}/receipt", json={"category": "Other", "keep": True, "expect_updated_at": ""})
check(r.status_code == 409 and r.json().get("receipt", {}).get("receipt", {}).get("category") == "Office",
      f"#6327: '' while it became a receipt meanwhile -> 409 with the current state {r.status_code} {r.text[:200]}")

older(D)
V0 = rc(Fr, D)["updated_at"]
# the laptop read V0; the phone changes the category (only that field)
r = Fr2.put(B + f"/api/docs/{D}/receipt", json={"category": "Travel", "expect_updated_at": V0})
check(r.status_code == 200, f"#6327: the phone with the current version -> 200 {r.status_code} {r.text[:200]}")
x = rc(Fr, D)
check(x["category"] == "Travel" and x["vat_pct"] == "19" and (x["project"] or {}).get("id") == P and x["is_receipt"],
      f"#6327: only the field sent changed (project and VAT rate stay) {x}")
V1 = x["updated_at"]
check(V1 != V0, "#6327: a new version")

# the laptop saves its VAT rate against V0 -> 409, nothing written
r = Fr.put(B + f"/api/docs/{D}/receipt", json={"vat_pct": "7", "expect_updated_at": V0})
check(r.status_code == 409, f"#6327: the laptop with the old version -> 409 (before: 400 unknown field, or the whole form put back) {r.status_code} {r.text[:200]}")
cur = r.json().get("receipt", {}) if r.status_code == 409 else {}
check(cur.get("receipt", {}).get("category") == "Travel" and cur["receipt"].get("updated_at") == V1, "#6327: the 409 carries the current state and version")
x = rc(Fr, D)
check(x["vat_pct"] == "19" and x["category"] == "Travel", "#6327: nothing of the refused save was written")
# against the current version: written, the category of the phone stays
r = Fr.put(B + f"/api/docs/{D}/receipt", json={"vat_pct": "7", "expect_updated_at": V1})
check(r.status_code == 200, f"#6327: again with the current version -> 200 {r.status_code} {r.text[:200]}")
x = rc(Fr, D)
check(x["vat_pct"] == "7" and x["category"] == "Travel" and (x["project"] or {}).get("id") == P, f"#6327: both changes are kept {x}")

# a canonical version in another spelling (Z instead of +00:00) is the same version
older(D)
V2 = rc(Fr, D)["updated_at"]
r = Fr.put(B + f"/api/docs/{D}/receipt", json={"category": "Travel", "expect_updated_at": V2.replace("+00:00", "Z")})
check(r.status_code == 200, f"#6327: the same instant written with Z -> no conflict {r.status_code} {r.text[:200]}")

# keep missing with a version: it stays a receipt even with nothing assigned
older(D)
V3 = rc(Fr, D)["updated_at"]
r = Fr.put(B + f"/api/docs/{D}/receipt", json={"category": "", "vat_pct": None, "project_id": None, "expect_updated_at": V3})
check(r.status_code == 200 and rc(Fr, D)["is_receipt"], f"#6327: emptied with a version, keep missing: still a receipt {r.status_code}")

# unknown fields stay refused
r = Fr.put(B + f"/api/docs/{D}/receipt", json={"amount": "1.00", "expect_updated_at": rc(Fr, D)["updated_at"]})
check(r.status_code == 400, f"#6327: an unknown field -> 400 {r.status_code}")

# without a version: the old behaviour (missing project / category = none)
D2 = upload("quittung.pdf")
check(Fr.put(B + f"/api/docs/{D2}/receipt", json={"category": "Office", "project_id": P, "keep": True}).ok, "setup: a second receipt")
r = Fr.put(B + f"/api/docs/{D2}/receipt", json={"vat_pct": "19", "keep": True})
x = rc(Fr, D2)
check(r.ok and x["category"] is None and x["project"] is None and x["vat_pct"] == "19", f"#6327: without a version as before {x}")

# the document's part: amount and date against edited_at (#4770, the sheet's PATCH)
r = Fr.patch(B + f"/api/docs/{D}", json={"amount": "119.00"})
E0 = r.json().get("edited_at")
r = Fr2.patch(B + f"/api/docs/{D}", json={"amount": "129.00", "expect_updated_at": E0})
check(r.status_code == 200, f"setup: the phone changes the amount {r.status_code} {r.text[:200]}")
E1 = r.json().get("edited_at")
if E1 != E0:  # a change in the same millisecond carries the same stamp; the check below needs two
    r = Fr.patch(B + f"/api/docs/{D}", json={"date": "2026-03-02", "expect_updated_at": E0})
    check(r.status_code == 409 and (r.json().get("doc") or {}).get("amount") in ("129.00", 129.0, "129"),
          f"#6327: the laptop's date against the old version of the document -> 409 {r.status_code} {r.text[:200]}")
r = Fr.patch(B + f"/api/docs/{D}", json={"date": "2026-03-02", "expect_updated_at": E1})
d = Fr.get(B + f"/api/docs/{D}").json()
check(r.status_code == 200 and d.get("date") == "2026-03-02" and str(d.get("amount")).startswith("129"), f"#6327: date saved, the amount of the phone stays {d.get('amount')}")

sys.exit(done("p21362_a_receipt_version"))
