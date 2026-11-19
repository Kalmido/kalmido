#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1327.0 (#1969, decision of 17.11.2026) API test, own container (hosted: there the records would really go).
An organisation or an account with finalised documents in their legal period is not deleted: 409 with the day and the way
(the retention export, then after the period or by the server's operator after the export). Invented people, companies and
figures only (example.com).
freelancer-matrix: office  tenant-matrix: org
 - a person without an organisation (personal office) with a finalised invoice: her own deletion request 409 (reason
   locked_docs, the day named), nothing changes (account not locked); her declared waiver does not open it either: the
   instance admin's deletion with it 409, nothing noted; after her export the operator's way (instance admin, ?retention=
   exported) deletes the account with its personal office
 - a person whose finalised invoice is past its period: goes as before (waiver)
 - 2.1413.0 (#6361): a finalised invoice is kept 8 years (+ the buffer), an offer of the same year 6: an invoice dated 8 years
   back still blocks, the same row as an offer is past its period and the account goes
 - a person with a draft invoice only: goes as before (no step)
 - an organisation with a finalised invoice: its admin's declared waiver does not let the instance admin delete it (409,
   locked_docs, the organisation and its document stay, nothing noted); after the admin's export it goes
usage: p21327_1969_locked_docs_test.py <datadir>"""
import base64
import os
import sys

import kt
from kt import B, check, su_get

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbx as dbxm  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

kt.docker_logs_on_first_fail()
DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
KEY = base64.b64encode(os.urandom(32)).decode()
OFC = "/api/office"
RX = "/api/retention"
COMPANY = {"name": "Studio Beispiel", "street": "Teststrasse 1", "zip": "20000", "city": "Hamburg", "country": "DE",
           "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001"}


def sql(q, args=(), write=False, locked_ok=False):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        if locked_ok:  # the switch of migrations.d/6467.py: this transaction may change a finalised document (backdating)
            c.execute("SELECT set_config('kalmido.locked_ok', 'on', true)")
        r = c.execute(q, args)
        if write:
            c.commit()
            return None
        return r.fetchall()
    finally:
        c.close()


def invoice(s, title="Schnitt", final=True):
    r = s.post(B + "/api/clients", json={"name": "Example Client Ltd " + title, "street": "Marktstrasse 5", "zip": "50000", "city": "Koeln", "country": "DE"})
    assert r.ok, r.text
    r = s.post(B + OFC + "/docs", json={"kind": "invoice", "client_id": r.json()["id"], "service_from": "2026-03-01", "service_to": "2026-03-02",
                                      "items": [{"title": title, "qty": 1, "rate": 120}]})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    if final:
        r = s.post(B + OFC + f"/docs/{did}/finalize")
        assert r.ok, r.text
    return did


def log(subject):
    return [x[0] for x in sql("SELECT kind FROM retention_log WHERE subject=? ORDER BY id", (subject,))]


def locked(r, did=None):
    """2.1413.0 (#6361): with did the day must be the invoice's own period (a receipt: 8 years + the buffer of 1, not 10 + 1 of a book)."""
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    want = f"{int(str(sql('SELECT date FROM office_docs WHERE id=?', (did,))[0][0])[:4]) + 9}-12-31" if did else None
    return (r.status_code == 409 and j.get("code") == "retention" and j.get("reason") == "locked_docs"
            and (j.get("kept_until") == want if want else (j.get("kept_until") or "") >= "2035"))


kt.fresh({"KALMIDO_HOSTED": "1", "KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ORGCRYPT_DELAY": "0", "KALMIDO_SECRET_KEY": KEY}, data=DATA)
A = kt.setup()

# ---------------------------------------------------------------- a person without an organisation  # freelancer-matrix: office
FID, Fr = freelancer(B, A, "frida")
assert Fr.put(B + OFC + "/settings", json={"company_fields": COMPANY}).ok
DID = invoice(Fr)
POID = sql("SELECT id FROM orgs WHERE personal_of=?", (FID,))[0][0]
r = Fr.post(B + "/api/account/delete", json={"password": kt.PASSWORD, "lists": {}, "retention": "waived"})
check(locked(r, DID) and "GoBD" in r.json().get("error", ""), f"#1969 #6361: her own deletion with a finalised invoice is refused (day and way named) {r.status_code} {r.text[:300]}")
check(sql("SELECT disabled, delete_at FROM users WHERE id=?", (FID,)) == [(False, None)], "#1969: refused: the account is not locked, no deletion planned")
check(Fr.post(B + RX + "/me/waiver").ok, "setup: frida declares the waiver")
r = A.delete(B + f"/api/users/{FID}", params={"retention": "waived"})
check(locked(r), f"#1969: her declared waiver does not let the instance admin delete it {r.status_code} {r.text[:300]}")
check(sql("SELECT 1 FROM users WHERE id=?", (FID,)) and sql("SELECT 1 FROM office_docs WHERE id=? AND locked_at IS NOT NULL", (DID,))
      and log(f"user:{FID}") == ["waiver_declared"], "#1969: account, personal office and invoice stay, no waiver is noted")
r = su_get(Fr, B + RX + "/me/export.zip")
check(r.ok and r.content.startswith(b"PK"), "setup: frida downloads her retention export")
r = A.delete(B + f"/api/users/{FID}", params={"retention": "exported"})
check(r.ok and not sql("SELECT 1 FROM users WHERE id=?", (FID,)) and not sql("SELECT 1 FROM orgs WHERE id=?", (POID,)),
      f"#1969: the operator's way after her export deletes the account with its personal office {r.status_code} {r.text[:300]}")

# a finalised invoice past its period: as before
HID, Hr = freelancer(B, A, "hanna")
assert Hr.put(B + OFC + "/settings", json={"company_fields": COMPANY}).ok
HDID = invoice(Hr, "Altfall")
sql("UPDATE office_docs SET date='2010-03-02', locked_at='2010-03-02T10:00:00+00:00' WHERE id=?", (HDID,), write=True, locked_ok=True)
check(Hr.post(B + RX + "/me/waiver").ok, "setup: hanna declares the waiver")
r = A.delete(B + f"/api/users/{HID}", params={"retention": "waived"})
check(r.ok and not sql("SELECT 1 FROM users WHERE id=?", (HID,)), f"#1969: past its period the invoice blocks nothing (as before) {r.status_code} {r.text[:300]}")

# 2.1413.0 (#6361): each finalised document by its kind -- an invoice 8 years, an offer (business letter) 6, + the buffer of 1
YEAR = int(sql("SELECT CAST(EXTRACT(YEAR FROM now()) AS INTEGER)")[0][0])
IID, Ir = freelancer(B, A, "ines")
assert Ir.put(B + OFC + "/settings", json={"company_fields": COMPANY}).ok
IDID = invoice(Ir, "Angebot alt")
sql("UPDATE office_docs SET date=?, locked_at=? WHERE id=?", (f"{YEAR - 8}-03-02", f"{YEAR - 8}-03-02T10:00:00+00:00", IDID), write=True, locked_ok=True)
check(Ir.post(B + RX + "/me/waiver").ok, "setup: ines declares the waiver")
r = A.delete(B + f"/api/users/{IID}", params={"retention": "waived"})
check(locked(r, IDID), f"#6361: an invoice of {YEAR - 8} is still kept (8 + 1 years) {r.status_code} {r.text[:300]}")
sql("UPDATE office_docs SET kind='offer' WHERE id=?", (IDID,), write=True, locked_ok=True)
r = A.delete(B + f"/api/users/{IID}", params={"retention": "waived"})
check(r.ok and not sql("SELECT 1 FROM users WHERE id=?", (IID,)),
      f"#6361: an offer of {YEAR - 8} is past its period (6 + 1 years, not 10 + 1 as a book): deleted {r.status_code} {r.text[:300]}")

# a draft only: as before
GID, Gr = freelancer(B, A, "gina")
assert Gr.put(B + OFC + "/settings", json={"company_fields": COMPANY}).ok
invoice(Gr, "Entwurf", final=False)
r = A.delete(B + f"/api/users/{GID}")
check(r.ok and not sql("SELECT 1 FROM users WHERE id=?", (GID,)), f"#1969: a draft invoice only: deleted as before {r.status_code} {r.text[:300]}")

# ---------------------------------------------------------------- an organisation  # tenant-matrix: org
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob", "password": kt.PASSWORD, "email": "bob@example.com", "orgs": []})
assert r.ok, r.text
Bo = kt.sess("bob")
r = Bo.post(B + "/api/orgs", json={"name": "Alpha Studio"})  # hosted: the customer creates its organisation itself
assert r.ok, r.text
ALPHA = r.json()["id"]
Bo.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": "office,clients,docs,files", "workspace": f"org:{ALPHA}"})
assert Bo.put(B + OFC + "/settings", json={"company_fields": dict(COMPANY, name="Alpha Studio GmbH")}).ok
ADID = invoice(Bo, "Alpha")
check(sql("SELECT org_id FROM office_docs WHERE id=?", (ADID,)) == [(ALPHA,)], "setup: the finalised invoice is Alpha's")
check(Bo.post(B + RX + f"/org/{ALPHA}/waiver").ok, "setup: Alpha's admin declares the waiver")
r = A.delete(B + f"/api/admin/orgs/{ALPHA}", params={"confirm": "1", "retention": "waived"})
check(locked(r, ADID), f"#1969: the organisation with a finalised invoice is not deleted with the waiver {r.status_code} {r.text[:300]}")
check(sql("SELECT 1 FROM orgs WHERE id=? AND retired_at IS NULL", (ALPHA,)) and sql("SELECT 1 FROM office_docs WHERE id=?", (ADID,))
      and log(f"org:{ALPHA}") == ["waiver_declared"], "#1969: the organisation and its invoice stay, no waiver is noted")
r = su_get(Bo, B + RX + f"/org/{ALPHA}/export.zip")
check(r.ok and r.content.startswith(b"PK"), "setup: Alpha's admin downloads the organisation's retention export")
r = A.delete(B + f"/api/admin/orgs/{ALPHA}", params={"confirm": "1", "retention": "exported"})
check(r.ok and not sql("SELECT 1 FROM orgs WHERE id=?", (ALPHA,)) and not sql("SELECT 1 FROM office_docs WHERE id=?", (ADID,)),
      f"#1969: after the export the operator deletes it {r.status_code} {r.text[:300]}")

sys.exit(kt.done("p21327_1969_locked_docs"))
