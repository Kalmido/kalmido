#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1291.0 (#6474, audit #4791 A4 to A7) API test, own container (hosted: after the retention gate the records really go).
The retention export before a deletion counts only when it is worth something, and only whose records these are does
without it. Invented people, companies and figures only (example.com).
freelancer-matrix: office  tenant-matrix: org
 - A7: a person whose only record is a received e-invoice nobody took over as a receipt: the deletion asks for the step
   (it went without one before), the ZIP has received-einvoices/ with the file byte for byte and its list
 - A6: an instance admin's ?retention=waived for another person is refused (409, reason waiver, nothing noted); the person
   declares the waiver (POST /api/retention/me/waiver; nothing to keep 409, an API token refused), then it goes
 - A4: an export in which a file could not be read does not open the gate (409, reason incomplete); the person sees the
   file's name, the deleting admin only the number; after a complete export it counts
 - A5: a record finalised after the export: the export no longer counts (409, reason newer) until it is downloaded again;
   a declared waiver ends as well when records are added
 - an organisation: only its admin declares the waiver (a member, another organisation's admin, the instance admin and an
   API token 404 / refused); it ends with a new record and when it is taken back; with it the instance admin deletes
 - the names of unreadable files leave the log with the deletion
usage: p21291_rxgate_test.py <datadir>"""
import base64
import io
import json
import os
import sys
import zipfile

import requests

import kt
from kt import B, check, su_get

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbx as dbxm  # noqa: E402
from freelancer_fixture import freelancer, org_join  # noqa: E402

kt.docker_logs_on_first_fail()
DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
KEY = base64.b64encode(os.urandom(32)).decode()
O = "/api/office"
RX = "/api/retention"
NOW = "2026-05-04T08:00:00+00:00"
COMPANY = {"name": "Studio Beispiel", "street": "Teststrasse 1", "zip": "20000", "city": "Hamburg", "country": "DE",
           "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001"}


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


def invoice(s, title="Schnitt"):
    r = s.post(B + "/api/clients", json={"name": "Example Client Ltd " + title, "street": "Marktstrasse 5", "zip": "50000", "city": "Koeln", "country": "DE"})
    assert r.ok, r.text
    r = s.post(B + O + "/docs", json={"kind": "invoice", "client_id": r.json()["id"], "service_from": "2026-03-01", "service_to": "2026-03-02",
                                      "items": [{"title": title, "qty": 1, "rate": 120}]})
    assert r.status_code == 201, r.text
    assert s.post(B + O + f"/docs/{r.json()['id']}/finalize").ok


def cash(s, text):
    j = s.get(B + O + "/cashbooks").json()
    r = s.post(B + f"{O}/cashbooks/{j['books'][0]['id']}/entries", json={"day": j["today"], "dir": "in", "amount": "15", "text": text, "vat_pct": "7"})
    assert r.status_code == 201, r.text


def einvoice(s, uid, number):
    """A received e-invoice in the person's documents space that is no receipt (as p2239_c_loeschung_test.py: the file through
    the app, what the recognition keeps of the invoice written directly) -> (node id, the file's bytes)."""
    r = s.post(B + "/api/files/folders", json={"name": "Invoices " + number})
    assert r.status_code == 201, r.text
    data = f"<Invoice><ID>{number}</ID></Invoice>\n".encode()
    r = s.post(B + "/api/files/upload", data={"parent_id": str(r.json()["id"])}, files={"file": ("invoice.xml", data)})
    assert r.ok, r.text
    nid = r.json()["items"][0]["id"]
    ex = json.dumps({"_einv": {"number": number, "seller": {"name": "Lieferant Beispiel GmbH"}, "gross": "119.00", "currency": "EUR"}})
    sql("INSERT INTO doc_meta(node_id, ws, state, extracted, doc_date, created_at, updated_at) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(node_id) DO UPDATE SET state=excluded.state, extracted=excluded.extracted, doc_date=excluded.doc_date",
        (nid, f"u{uid}", "done", ex, "2026-02-01", NOW, NOW), write=True)
    return nid, data


def unzip(r):
    return zipfile.ZipFile(io.BytesIO(r.content))


def log(subject):
    return [x[0] for x in sql("SELECT kind FROM retention_log WHERE subject=? ORDER BY id", (subject,))]


kt.fresh({"KALMIDO_HOSTED": "1", "KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ORGCRYPT_DELAY": "0", "KALMIDO_SECRET_KEY": KEY}, data=DATA)
A = kt.setup()
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ag = A.post(B + "/api/admin/agents", json={"scopes": ["read", "tasks:write", "comments"], "username": "claude", "display_name": "Claude"}).json()
AGH = {"Authorization": "Bearer " + ag["token"], "X-Requested-With": "kalmido"}

# ---------------------------------------------------------------- A7: a received e-invoice is a record to keep
EID, Er = freelancer(B, A, "erik")
ENID, EXML = einvoice(Er, EID, "ER-2026-77")
j = Er.get(B + RX + "/me").json()
check(j.get("hosted") is True and j.get("needed") is True and j.get("counts") == {"einvoices": 1}, f"A7: the received e-invoice is counted {j}")
r = A.delete(B + f"/api/users/{EID}")
check(r.status_code == 409 and r.json().get("code") == "retention" and sql("SELECT 1 FROM users WHERE id=?", (EID,)),
      f"A7: an account with only a received e-invoice is not deleted without the step {r.status_code} {r.text[:200]}")
r = su_get(Er, B + RX + "/me/export.zip")
z = unzip(r) if r.ok else None
names = z.namelist() if z else []
ef = [n for n in names if n.startswith(f"received-einvoices/{ENID}-")]
ecsv = z.read("received-einvoices/received-einvoices.csv").decode("utf-8-sig") if "received-einvoices/received-einvoices.csv" in names else ""
check(len(ef) == 1 and z.read(ef[0]) == EXML, f"A7: the e-invoice file in the ZIP, byte for byte {names}")
check("ER-2026-77" in ecsv and "Lieferant Beispiel GmbH" in ecsv and "119.00" in ecsv, "A7: its list names number, seller and amount\n" + ecsv[:300])
check("received-einvoices/" in (z.read("00-index.txt").decode() if z else ""), "A7: the index names the section")
r = A.delete(B + f"/api/users/{EID}", params={"retention": "exported"})
check(r.ok and not sql("SELECT 1 FROM users WHERE id=?", (EID,)), "A7: after the export the account goes " + r.text[:200])

# ---------------------------------------------------------------- a person without an organisation  # freelancer-matrix: office
FID, Fr = freelancer(B, A, "frida")
assert Fr.put(B + O + "/settings", json={"company_fields": COMPANY}).ok
invoice(Fr)
BL = Fr.post(B + "/api/budget/lists", json={}).json().get("list_id")
e = Fr.post(B + f"/api/budget/{BL}/entries", json={"day": "2026-09-05", "amount": 7, "kind": "out", "title": "Tape"}).json()
assert Fr.post(B + f"/api/budget/entries/{e['id']}/files", files=[("file", ("tape.txt", b"tape", "text/plain"))]).ok
DEL = {"lists": "delete", "confirm": "frida"}
j = Fr.get(B + RX + "/me").json()
check(j.get("needed") and j.get("can_waive") is True and j.get("may_declare") is True and j.get("waived_at") is None and j.get("export_problem") is None,
      f"setup: frida's records, she may do without the export herself {j}")

# A6: the instance admin does not waive for her
ri = A.get(B + f"/api/users/{FID}/delete-info").json().get("retention", {})
check(ri.get("needed") and ri.get("can_waive") is False and ri.get("may_declare") is False and "counts" not in ri, f"A6: delete-info: the admin cannot waive {ri}")
r = A.delete(B + f"/api/users/{FID}", params={**DEL, "retention": "waived"})
check(r.status_code == 409 and r.json().get("code") == "retention" and r.json().get("reason") == "waiver",
      f"A6: the instance admin's waiver for another person is refused {r.status_code} {r.text[:200]}")
check(sql("SELECT 1 FROM users WHERE id=?", (FID,)) and sql("SELECT 1 FROM lists WHERE id=?", (BL,)) and log(f"user:{FID}") == [],
      "A6: refused: account and project stay, nothing is noted")
r = A.post(B + "/api/retention/me/waiver")
check(r.status_code == 409 and r.json().get("code") == "nothing", f"waiver: nothing to keep (the admin's own account) 409 {r.status_code}")
r = requests.post(B + "/api/retention/me/waiver", headers=AGH)
check(r.status_code in (401, 403) and log(f"user:{FID}") == [], f"waiver: an API token declares nothing {r.status_code}")

# A4: an export in which a file could not be read
PATH = sql("SELECT path FROM budget_files WHERE list_id=?", (BL,))[0][0]
sql("UPDATE budget_files SET path='gone/none.bin' WHERE list_id=?", (BL,), write=True)
r = su_get(Fr, B + RX + "/me/export.zip")
man = json.loads(unzip(r).read("manifest.json")) if r.ok else {}
check(r.ok and len(man.get("missing") or []) == 1 and "tape.txt" in man["missing"][0], f"A4 setup: the ZIP names the unreadable file {man.get('missing')}")
j = Fr.get(B + RX + "/me").json()
p = j.get("export_problem") or {}
check(j.get("exported_at") is None and p.get("reason") == "incomplete" and p.get("missing") == 1 and any("tape.txt" in n for n in p.get("missing_names") or []),
      f"A4: the person sees that the export does not count, with the file's name {j.get('exported_at')} {p}")
p = (A.get(B + f"/api/users/{FID}/delete-info").json().get("retention") or {}).get("export_problem") or {}
check(p.get("reason") == "incomplete" and p.get("missing") == 1 and "missing_names" not in p, f"A4: the deleting admin sees the number, no names {p}")
r = A.delete(B + f"/api/users/{FID}", params={**DEL, "retention": "exported"})
check(r.status_code == 409 and r.json().get("reason") == "incomplete" and "tape.txt" not in r.text and sql("SELECT 1 FROM users WHERE id=?", (FID,)),
      f"A4: an incomplete export does not open the gate {r.status_code} {r.text[:300]}")
sql("UPDATE budget_files SET path=? WHERE list_id=?", (PATH, BL), write=True)
r = su_get(Fr, B + RX + "/me/export.zip")
check(r.ok and not json.loads(unzip(r).read("manifest.json")).get("missing"), "A4: the next export is complete")
j = Fr.get(B + RX + "/me").json()
check(j.get("exported_at") and j.get("export_problem") is None, f"A4: the complete export counts {j}")

# A5: a record after the export
invoice(Fr, "Nachdreh")
j = Fr.get(B + RX + "/me").json()
p = j.get("export_problem") or {}
check(j.get("exported_at") is None and p.get("reason") == "newer" and p.get("newer") == 1, f"A5: an invoice finalised after the export: it no longer counts {j}")
r = A.delete(B + f"/api/users/{FID}", params={**DEL, "retention": "exported"})
check(r.status_code == 409 and r.json().get("reason") == "newer" and sql("SELECT 1 FROM users WHERE id=?", (FID,)),
      f"A5: the deletion asks for a new export {r.status_code} {r.text[:300]}")

# A6: her own declaration, and it ends with a new record / when she takes it back
r = Fr.post(B + "/api/retention/me/waiver")
check(r.ok and r.json().get("waived_at") and log(f"user:{FID}")[-1] == "waiver_declared", f"A6: frida declares the waiver {r.status_code} {r.text[:200]}")
check(A.get(B + f"/api/users/{FID}/delete-info").json()["retention"].get("waived_at"), "A6: the admin's dialog sees the declaration")
cash(Fr, "Barverkauf Markt")
check(Fr.get(B + RX + "/me").json().get("waived_at") is None, "A6: a new record ends the declaration")
r = A.delete(B + f"/api/users/{FID}", params={**DEL, "retention": "waived"})
check(r.status_code == 409 and r.json().get("reason") == "waiver", f"A6: the outdated declaration does not open the gate {r.status_code}")
check(Fr.post(B + "/api/retention/me/waiver").json().get("waived_at"), "A6: declared again")
r = Fr.delete(B + "/api/retention/me/waiver")
check(r.ok and r.json().get("waived_at") is None and log(f"user:{FID}")[-1] == "waiver_revoked", f"A6: taken back {r.status_code} {r.text[:200]}")
r = A.delete(B + f"/api/users/{FID}", params={**DEL, "retention": "waived"})
check(r.status_code == 409 and sql("SELECT 1 FROM users WHERE id=?", (FID,)), f"A6: after taking it back: refused again {r.status_code}")

# the complete, current export: the account goes; the names of the unreadable file leave the log
check(sql("SELECT COUNT(*) FROM retention_log WHERE subject=? AND jsonb_exists(detail, 'missing_names') AND detail::text LIKE '%tape.txt%'", (f"user:{FID}",))[0][0] == 1,
      "setup: the log row of the incomplete export names the file")
r = su_get(Fr, B + RX + "/me/export.zip")
check(r.ok and Fr.get(B + RX + "/me").json().get("exported_at"), "the export after the last record counts")
r = A.delete(B + f"/api/users/{FID}", params={**DEL, "retention": "exported"})
check(r.ok and not sql("SELECT 1 FROM users WHERE id=?", (FID,)) and not sql("SELECT 1 FROM lists WHERE id=?", (BL,)),
      f"after the complete, current export the account goes with its project {r.status_code} {r.text[:200]}")
check(sql("SELECT COUNT(*) FROM retention_log WHERE subject=? AND kind='export'", (f"user:{FID}",))[0][0] == 3
      and sql("SELECT COUNT(*) FROM retention_log WHERE subject=? AND detail::text LIKE '%tape.txt%'", (f"user:{FID}",))[0][0] == 0,
      "the export rows outlive the account without the file names")

# ---------------------------------------------------------------- an organisation  # tenant-matrix: org
ids = {}
for u in ("bob", "carol", "dave"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": kt.PASSWORD, "email": f"{u}@example.com", "orgs": []})
    assert r.ok, r.text
    ids[u] = r.json()["id"]
Bo, Ca, Da = kt.sess("bob"), kt.sess("carol"), kt.sess("dave")
# hosted: a customer creates its organisation itself (2.399.0 #2687: the operator creates none for somebody else)
r1, r2 = Bo.post(B + "/api/orgs", json={"name": "Alpha Studio"}), Da.post(B + "/api/orgs", json={"name": "Beta AG"})
assert r1.ok and r2.ok, r1.text + r2.text
ALPHA, BETA = r1.json()["id"], r2.json()["id"]
# 2.593.0 (#3570): an invitation by e-mail into a company of its own reaches only a person its admin may see: connected first
sql("INSERT INTO conn_links(a_id, b_id, created_at) VALUES(?, ?, '2026-01-01T00:00:00Z')", tuple(sorted((ids["bob"], ids["carol"]))), write=True)
kt.proved()  # 2.1021.0 (#5775): an organisation admin invites by address only an account that proved it
assert Bo.put(B + f"/api/orgs/{ALPHA}/members", json={"email": "carol@example.com", "role": "member"}).ok
assert org_join(B, "carol", ALPHA), "setup: carol is a member of Alpha"
for s, o in ((Bo, ALPHA), (Ca, ALPHA), (Da, BETA)):
    s.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": "cal,comments,collab,office,clients,docs,files", "workspace": f"org:{o}"})
assert Bo.put(B + O + "/settings", json={"company_fields": dict(COMPANY, name="Alpha Studio GmbH")}).ok
cash(Bo, "Kasse Alpha")
check(Bo.get(B + RX + f"/org/{ALPHA}").json().get("counts", {}).get("cash") == 1 and Bo.get(B + RX + f"/org/{ALPHA}").json().get("may_declare") is True,
      "setup: Alpha keeps a cash book entry, its admin may declare")
ri = A.get(B + RX + f"/org/{ALPHA}").json()
check(ri.get("needed") and ri.get("can_waive") is False and ri.get("may_declare") is False, f"A6: the instance admin cannot waive for Alpha {ri}")
r = A.delete(B + f"/api/admin/orgs/{ALPHA}", params={"confirm": "1", "retention": "waived"})
check(r.status_code == 409 and r.json().get("reason") == "waiver" and sql("SELECT 1 FROM orgs WHERE id=?", (ALPHA,)) and log(f"org:{ALPHA}") == [],
      f"A6: the instance admin's waiver for a customer's organisation is refused {r.status_code} {r.text[:200]}")
for who, s in (("a member", Ca), ("another organisation's admin", Da), ("the instance admin", A)):
    r1, r2 = s.post(B + f"/api/retention/org/{ALPHA}/waiver"), s.delete(B + f"/api/retention/org/{ALPHA}/waiver")
    check(r1.status_code == 404 and r2.status_code == 404, f"waiver of Alpha: {who} 404 {r1.status_code} {r2.status_code}")
r = requests.post(B + f"/api/retention/org/{ALPHA}/waiver", headers=AGH)
check(r.status_code in (401, 403, 404) and log(f"org:{ALPHA}") == [], f"waiver of Alpha: an API token refused, nothing noted {r.status_code}")
r = Bo.post(B + f"/api/retention/org/{ALPHA}/waiver")
check(r.ok and r.json().get("waived_at") and A.get(B + RX + f"/org/{ALPHA}").json().get("waived_at"), f"A6: Alpha's admin declares the waiver {r.status_code} {r.text[:200]}")
cash(Bo, "Kasse Alpha zwei")
check(A.get(B + RX + f"/org/{ALPHA}").json().get("waived_at") is None, "A6: a new cash book entry ends Alpha's declaration")
r = A.delete(B + f"/api/admin/orgs/{ALPHA}", params={"confirm": "1", "retention": "waived"})
check(r.status_code == 409 and sql("SELECT 1 FROM orgs WHERE id=?", (ALPHA,)), f"A6: the outdated declaration does not delete Alpha {r.status_code}")
check(Bo.post(B + f"/api/retention/org/{ALPHA}/waiver").ok and Bo.delete(B + f"/api/retention/org/{ALPHA}/waiver").json().get("waived_at") is None,
      "A6: declared again and taken back")
check(A.delete(B + f"/api/admin/orgs/{ALPHA}", params={"confirm": "1", "retention": "waived"}).status_code == 409, "A6: taken back: refused")
check(Bo.post(B + f"/api/retention/org/{ALPHA}/waiver").ok, "A6: declared for good")
r = A.delete(B + f"/api/admin/orgs/{ALPHA}", params={"confirm": "1", "retention": "waived"})
check(r.ok and not sql("SELECT 1 FROM orgs WHERE id=?", (ALPHA,)), f"A6: with the admin's declaration the instance admin deletes Alpha {r.status_code} {r.text[:300]}")
row = sql("SELECT kind, by_user, detail->>'declared_by' FROM retention_log WHERE subject=? ORDER BY id DESC LIMIT 1", (f"org:{ALPHA}",))
check(row == [("waiver", ALICE, str(ids["bob"]))], f"A6: the waiver is noted with who deleted and who declared {row}")

sys.exit(kt.done("p21291_rxgate"))
