#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1497.0 API tests (#7662): "Recently edited" (GET /api/recent, the shared core of #5352) also for the office and Tables,
own container (start.sh). Invented data only.
 - office: quotations, invoices, the office's clients and its receipts, each with area "office" and its kind; every
   organisation's office through the office's OWN check (office_role, office_can): the admin sees all, a member with the
   previous access the quotations / invoices / clients but no receipts (the bookkeeping is the admins'), a member in the
   office group "No office access" nothing of the office, another organisation's admin nothing and ?space=org:<other> 404
 - a receipt once (as the office's), not a second time as a file
 - tables: the tables' own visibility (sh_index): the organisation's table for its members, never another person's private
   table, nothing of another organisation; ?space= narrows; areas=office / sheets narrows
 - an area the organisation's admins switch off gives nothing of it (office, sheets)
 - a person without an organisation sees her own personal office and her tables in Private (freelancer-matrix: office)
tenant-matrix: recent
usage: p21497_b_recent_api_test.py <datadir>      (KMT_NOSTART=1 / P21497B_NOSTART=1: a running server)"""
import sys

from freelancer_fixture import FEATURES, freelancer, login
from kt import B, check, done, fresh, setup

fresh(prefix="P21497B")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEATURES})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
COMPANY = {"name": "Studio Example GmbH", "street": "Hafenweg 1", "zip": "20457", "city": "Hamburg", "country": "de",
           "email": "hello@studio.example", "tax_number": "12/345/67890", "vat_id": "DE999999999", "iban": "DE02120300000000202051",
           "bic": "BYLADEM1001", "bank_name": "Example Bank"}


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
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)


def mkorg(name, admin):
    r = A.post(B + "/api/admin/orgs", json={"name": name, "admin_id": admin})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def mkuser(name, orgs):
    r = A.post(B + "/api/users", json={"username": name, "display_name": name.title(), "password": "password123",
                                       "email": f"{name}@example.com", "orgs": orgs})
    assert r.ok, r.text
    s = login(B, name)
    s.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEATURES})
    return r.json()["id"], s


def ws(s, space):
    """The office works in the workspace of the setting (office_org)."""
    assert s.patch(B + "/api/settings", json={"workspace": space}).ok


def client(s, name, org):
    r = s.post(B + "/api/clients", json={"name": name, "country": "DE", "org_id": org})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def office_doc(s, kind, cl, title):
    r = s.post(B + "/api/office/docs", json={"kind": kind, "client_id": cl, "project_title": title})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def receipt(s, space, name):
    r = s.post(B + "/api/docs", data={"ws": space}, files={"files": (name, tiny_pdf("Beleg " + name), "application/pdf")})
    assert r.status_code == 201, r.text
    nid = r.json()["ids"][0]
    assert s.patch(B + f"/api/docs/{nid}", json={"date": "2026-04-01", "amount": "11.90"}).ok
    r = s.put(B + f"/api/docs/{nid}/receipt", json={"category": "Office", "vat_pct": "19", "keep": True})
    assert r.ok, r.text
    return nid


def sheet(s, space, title):
    r = s.post(B + "/api/sheets", json={"title": title, "space": space})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def recent(s, **params):
    r = s.get(B + "/api/recent", params={"limit": 50, **params})
    return r.json().get("items", []) if r.ok else None


def keys(items):
    return {(x["area"], x.get("kind", ""), x["id"]) for x in items or []}


def office(items):
    return {k for k in keys(items) if k[0] == "office"}


ORG = mkorg("Nordwind", ALICE)
BOB, Bo = mkuser("bob", [ORG])
CARL, Ca = mkuser("carl", [ORG])
DORA, Do = mkuser("dora", [])
ORG2 = mkorg("Suedwind", DORA)
SP, SP2 = f"org:{ORG}", f"org:{ORG2}"
for s, sp in ((A, SP), (Bo, SP), (Ca, SP), (Do, SP2)):
    ws(s, sp)
check(A.put(B + "/api/office/settings", json={"company_fields": COMPANY, "lang": "en", "currency": "EUR"}).ok, "setup: Nordwind's office")
check(Do.put(B + "/api/office/settings", json={"company_fields": {**COMPANY, "name": "Suedwind"}, "lang": "en", "currency": "EUR"}).ok, "setup: Suedwind's office")
check(A.put(B + f"/api/office/rights/people/{CARL}", json={"groups": ["tpl:none"]}).ok, "setup: carl in the office group 'No office access'")

# ---- the content
CL = client(A, "Example Client AG", ORG)
OFF = office_doc(A, "offer", CL, "Image film")
INV = office_doc(A, "invoice", CL, "Image film")
RC = receipt(A, SP, "team-receipt.pdf")
SH_ORG = sheet(A, SP, "Shoot budget")
SH_PRIV = sheet(A, "private", "Alice private table")
CL2 = client(Do, "Suedwind Client", ORG2)
OFF2 = office_doc(Do, "offer", CL2, "Secret")
SH_ORG2 = sheet(Do, SP2, "Suedwind table")
O_ALL = {("office", "offer", OFF), ("office", "invoice", INV), ("office", "client", CL), ("office", "receipt", RC)}
O_OTHER = {("office", "offer", OFF2), ("office", "client", CL2)}

# ================================================================== the office's admin: all four kinds, with workspace and title
it = recent(A)
k = keys(it)
check(O_ALL <= k, f"#7662: alice (admin) sees quotation, invoice, client and receipt of Nordwind's office {sorted(office(it))}")
check(not k & O_OTHER and ("sheets", "", SH_ORG2) not in k, "#7662: nothing of another organisation's office or tables")
check({("sheets", "", SH_ORG), ("sheets", "", SH_PRIV)} <= k, f"#7662: alice sees her tables {sorted(k)}")
x = next(x for x in it if x["area"] == "office" and x["id"] == CL and x["kind"] == "client")
check(x["space"] == SP and x["title"] == "Example Client AG" and x["by"] == ALICE and x["at"], f"#7662: a client: workspace, title, who, when {x}")
x = next(x for x in it if x["area"] == "office" and x["id"] == OFF and x["kind"] == "offer")
check(x["space"] == SP and x["title"] and x["at"], f"#7662: a quotation {x}")
x = next(x for x in it if x["area"] == "sheets" and x["id"] == SH_ORG)
check(x["space"] == SP and x["title"] == "Shoot budget" and x["by"] == ALICE, f"#7662: a table {x}")
check(("files", "", RC) not in k, "#7662: the receipt once, as the office's (not again as a file)")
ats = [x["at"][:19] + (x["at"][19:23] if x["at"][19:20] == "." else ".000") for x in it]
check(ats == sorted(ats, reverse=True), f"#7662: newest first {ats}")
check({x["area"] for x in recent(A, areas="office")} == {"office"} and {x["area"] for x in recent(A, areas="sheets")} == {"sheets"},
      "#7662: areas=office / sheets narrows")
check(all(x["space"] == "private" for x in recent(A, space="private")) and ("sheets", "", SH_PRIV) in keys(recent(A, space="private"))
      and not office(recent(A, space="private")) & O_ALL, "#7662: ?space=private: her private table, nothing of Nordwind's office")

# ================================================================== a member with the previous access: quotations / invoices / clients, no receipts
it = recent(Bo)
k = keys(it)
check({("office", "offer", OFF), ("office", "invoice", INV), ("office", "client", CL)} <= k,
      f"#7662: bob (member) sees the office's quotation, invoice and client {sorted(office(it))}")
check(("office", "receipt", RC) not in k, "#7662: bob: no receipt (the bookkeeping is the office admins')")
check(("sheets", "", SH_ORG) in k and ("sheets", "", SH_PRIV) not in k, "#7662: bob: the organisation's table, never alice's private one")
check(not k & O_OTHER and ("sheets", "", SH_ORG2) not in k, "#7662: bob: nothing of another organisation")
check(bool(office(recent(Bo, space=SP))) and all(x["space"] == SP for x in recent(Bo, space=SP)), "#7662: bob ?space=org: only Nordwind")

# ================================================================== a member without office rights: nothing of the office, the tables stay
it = recent(Ca)
check(not office(it), f"#7662: carl (office group 'No office access') sees nothing of the office {sorted(office(it))}")
check(("sheets", "", SH_ORG) in keys(it), "#7662: carl still sees the organisation's table (its own visibility)")

# ================================================================== another organisation: 404, nothing of it
check(Do.get(B + "/api/recent", params={"space": SP}).status_code == 404, "#7662: dora: Nordwind 404")
k = keys(recent(Do))
check({("office", "offer", OFF2), ("office", "client", CL2), ("sheets", "", SH_ORG2)} <= k and not k & O_ALL and ("sheets", "", SH_ORG) not in k,
      f"#7662: dora: Suedwind's office and table only {sorted(k)}")

# ================================================================== switched off by the organisation's admins
check(A.patch(B + f"/api/orgs/{ORG}", json={"areas_off": ["office", "sheets"]}).ok, "setup: Nordwind switches the office and Tables off")
k = keys(recent(Bo))
check(not k & O_ALL and ("sheets", "", SH_ORG) not in k, f"#7662: switched off: nothing of the office / tables of Nordwind {sorted(k)}")
A.patch(B + f"/api/orgs/{ORG}", json={"areas_off": []})
check(("office", "offer", OFF) in keys(recent(Bo)), "#7662: on again: there again")

# ================================================================== a person without an organisation (freelancer-matrix: office)
FID, Fr = freelancer(B, A)
check(Fr.put(B + "/api/office/settings", json={"company_fields": {**COMPANY, "name": "Frida Photo"}, "lang": "en", "currency": "EUR"}).ok,
      "freelancer: her personal office")
FCL = client(Fr, "Frida's Client", None)
FOFF = office_doc(Fr, "offer", FCL, "Wedding")
FRC = receipt(Fr, "private", "frida-receipt.pdf")
FSH = sheet(Fr, "private", "Frida table")
it = recent(Fr)
k = keys(it)
check({("office", "offer", FOFF), ("office", "client", FCL), ("office", "receipt", FRC), ("sheets", "", FSH)} <= k
      and all(x["space"] == "private" for x in it), f"freelancer: her personal office and table, in Private {sorted(k)}")
check(not k & O_ALL and not k & O_OTHER, "freelancer: nothing of any organisation")
check(keys(recent(Fr, space="private")) == k, "freelancer: ?space=private the same")
check(not office(recent(A)) & {("office", "offer", FOFF), ("office", "client", FCL)}, "freelancer: her office is not alice's")

sys.exit(done("p21497_b_recent_api_test"))
