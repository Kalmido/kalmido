#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1316.0 (#6577): an organisation import into an office that has documents already is no silent merge. Invented companies,
people and figures only.
 - the source organisation finalises two invoices; the stored original of the second is gone before the export (its number
   no longer names the stored file)
 - into an organisation whose first invoice has the same number: the preview names the number for that target, says how many
   finalised documents the file brings (the undo keeps them) and which original is missing; the start is refused (409) with
   the list, nothing is written, the upload stays at its preview
 - into an organisation locked up to a month the file has data of: the preview and the start name the locked month (409)
 - into an empty organisation: no conflict, the import runs; the invoice with its original arrives and opens, the one without
   its original does not arrive and the result names its number
 - a person without organisation (P4) with an invoice of the same number in her personal office: target "private" is refused
   the same way
Its own container (KALMIDO_SECRET_KEY: the organisation export needs it).
usage: p6577_import_target_test.py <datadir>"""
# freelancer-matrix: office
import base64
import json
import os
import sys
import time

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import B, check, dbx, done, fresh, setup, su_get  # noqa: E402

OFF_API, D = "/api/office", "/api/office/docs"
KEY = base64.b64encode(os.urandom(32)).decode()
OLD = "2025-03-05"  # the source's invoices are dated here (a finished month a target can lock)
COMPANY = {"street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE", "email": "hallo@beispiel.example",
           "vat_id": "DE123456789", "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}


def upload(s, data):
    r = s.post(B + "/api/account/import", json={"size": len(data), "name": "beispiel.kalmido-export"})
    assert r.ok, r.text
    iid, off = r.json()["id"], 0
    while off < len(data):
        part = data[off:off + (1 << 20)]
        r = s.put(B + f"/api/account/import/{iid}?offset={off}", data=part, headers={"Content-Type": "application/octet-stream"})
        assert r.ok, r.text
        off += len(part)
    return iid


def wait(s, iid, secs=240):
    j = {}
    for _ in range(secs * 4):
        j = s.get(B + f"/api/account/import/{iid}").json()
        if j.get("state") not in ("checking", "running", "upload"):
            return j
        time.sleep(0.25)  # polls the import's own state (a real state, the loop ends as soon as it changes)
    return j


def opened(s, data, rk):
    iid = upload(s, data)
    j = wait(s, iid)
    if j.get("state") == "key":
        check(s.post(B + f"/api/account/import/{iid}/key", json={"recovery_key": rk}).status_code == 202, "the recovery key is taken")
        j = wait(s, iid)
    check(j.get("state") == "preview", f"opened {j.get('state')} {j.get('error')}")
    return iid, j.get("preview") or {}


def start(s, iid, target):
    return s.post(B + f"/api/account/import/{iid}/run", json={"again": True, "target": target, "people": {}})


def export(s, oid):
    r = s.post(B + f"/api/orgs/{oid}/export")
    check(r.status_code == 202, f"export started {r.status_code} {r.text[:160]}")
    for _ in range(960):
        if s.get(B + f"/api/orgs/{oid}/export").json().get("state") != "running":
            break
        time.sleep(0.25)  # polls the export's own state
    data = su_get(s, B + f"/api/orgs/{oid}/export/file").content
    rk = s.post(B + f"/api/orgs/{oid}/encryption/recovery", json={"password": "password123"}).json().get("recovery_key", "")
    check(data[:13] == b"KALMIDO-ORGX\n", f"export of {oid}")
    return data, rk


def office(s, name):
    assert s.put(B + OFF_API + "/settings", json={"lang": "de", "company_fields": {**COMPANY, "name": name}}).ok


def invoice(s, title):
    """A finalised invoice of the current workspace -> (id, number)."""
    r = s.post(B + "/api/clients", json={"name": "Muster Medien AG", "street": "Marktweg 5", "zip": "50667", "city": "Koeln", "country": "DE"})
    assert r.status_code in (200, 201), r.text
    r = s.post(B + D, json={"kind": "invoice", "lang": "de", "client_id": r.json()["id"], "items": [{"title": title, "qty": 1, "rate": 500}]})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    r = s.post(B + f"{D}/{did}/finalize")
    assert r.ok and r.json().get("locked"), r.text
    return did, r.json()["number"]


def docs(oid):
    return sorted(x[0] for x in dbx("SELECT number FROM office_docs WHERE org_id=? AND number<>''", (oid,)))


def conflicts(pv, target):
    return (((pv.get("office") or {}).get("targets") or {}).get(str(target)) or {}).get("conflicts") or []


fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_SECRET_KEY": KEY})
A = setup()
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Quelle", "admin_id": ALICE}).json()["id"]
ORG_T = A.post(B + "/api/admin/orgs", json={"name": "Ziel mit Rechnung", "admin_id": ALICE}).json()["id"]
ORG_L = A.post(B + "/api/admin/orgs", json={"name": "Ziel gesperrt", "admin_id": ALICE}).json()["id"]
ORG_E = A.post(B + "/api/admin/orgs", json={"name": "Ziel leer", "admin_id": ALICE}).json()["id"]
assert A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG}"}).ok

# ================================================================== the source: two finalised invoices, one original gone
office(A, "Quelle GmbH")
I1, N1 = invoice(A, "Schnitt")
I2, N2 = invoice(A, "Ton")
PDF1 = A.get(B + f"{D}/{I1}/pdf").content
dbx(f"UPDATE office_docs SET date='{OLD}' WHERE org_id={int(ORG)}")
GONE = "GONE-6577"  # the stored file keeps the old number in its name: the export carries no original for this number
dbx("DO $$ BEGIN PERFORM set_config('kalmido.locked_ok', 'on', true); "
    f"UPDATE office_docs SET number='{GONE}' WHERE id={int(I2)}; END $$")
check(A.get(B + f"{D}/{I2}/pdf").status_code == 409, "the source: the invoice without its stored original answers 409")
OX, RK = export(A, ORG)

# ================================================================== a target with an invoice of the same number
assert A.patch(B + "/api/settings", json={"workspace": f"org:{ORG_T}"}).ok
office(A, "Ziel GmbH")
_t, NT = invoice(A, "Eigene Leistung")
check(NT == N1, f"the target's first invoice has the number of the source's first one {NT} {N1}")
before = docs(ORG_T)
iid, pv = opened(A, OX, RK)
oc = pv.get("office") or {}
check(any(N1 in x for x in conflicts(pv, ORG_T)), f"the preview names the colliding number for this target {conflicts(pv, ORG_T)}")
check(not conflicts(pv, ORG_E), f"... and none for the empty organisation {conflicts(pv, ORG_E)}")
check(oc.get("final") == 2, f"the preview counts the finalised documents (the undo keeps them) {oc.get('final')}")
check(oc.get("missing") == [GONE], f"the preview names the finalised document without its original {oc.get('missing')}")
r = start(A, iid, ORG_T)
check(r.status_code == 409 and any(N1 in x for x in r.json().get("conflicts", [])) and N1 in r.json().get("error", ""),
      f"the start is refused with the list {r.status_code} {r.text[:300]}")
check(docs(ORG_T) == before, f"nothing of the file in the target {docs(ORG_T)}")
check(A.get(B + f"/api/account/import/{iid}").json().get("state") == "preview", "the upload stays at its preview (another target can be chosen)")

# ================================================================== a target locked up to a month the file has data of
assert A.patch(B + "/api/settings", json={"workspace": f"org:{ORG_L}"}).ok
r = A.post(B + OFF_API + "/periods/lock", json={"through": "2025-06", "confirm": "06/2025"})
check(r.ok, f"the target locks up to 06/2025 {r.status_code} {r.text[:160]}")
A.delete(B + f"/api/account/import/{iid}")
iid, pv = opened(A, OX, RK)
check(any("06/2025" in x and "03/2025" in x for x in conflicts(pv, ORG_L)), f"the preview names the locked month {conflicts(pv, ORG_L)}")
r = start(A, iid, ORG_L)
check(r.status_code == 409 and "06/2025" in r.json().get("error", ""), f"the start into the locked office is refused {r.status_code} {r.text[:300]}")
check(not docs(ORG_L), "nothing in the locked office")

# ================================================================== into an empty organisation
r = start(A, iid, ORG_E)
check(r.status_code == 202, f"the start into the empty organisation runs {r.status_code} {r.text[:200]}")
j = wait(A, iid)
check(j.get("state") == "done", f"import done {j.get('state')} {j.get('error')}")
w = json.dumps((j.get("result") or {}).get("warnings") or [], ensure_ascii=False)
check("without its original file" in w and GONE in w, f"the result names the document without its original {w[:600]}")
check(docs(ORG_E) == [N1], f"only the invoice with its original arrived {docs(ORG_E)}")
assert A.patch(B + "/api/settings", json={"workspace": f"org:{ORG_E}"}).ok
got = [x for x in A.get(B + D + "?kind=invoice").json().get("docs", []) if x.get("number") == N1]
check(len(got) == 1 and A.get(B + f"{D}/{got[0]['id']}/pdf").content == PDF1, "the imported invoice opens with its original PDF")
A.delete(B + f"/api/account/import/{iid}")

# ================================================================== P4: a person without organisation, target "private"
FID, Fr = freelancer(B, A)
office(Fr, "Frida Schnitt")
_f, NF = invoice(Fr, "Frida Leistung")
check(NF == N1, f"P4: her first invoice has the same number {NF} {N1}")
iid, pv = opened(Fr, OX, RK)
check(any(N1 in x for x in conflicts(pv, "private")), f"P4: the preview names the number for her private office {conflicts(pv, 'private')}")
r = start(Fr, iid, "private")
check(r.status_code == 409 and any(N1 in x for x in r.json().get("conflicts", [])), f"P4: the start is refused {r.status_code} {r.text[:200]}")
PB = dbx("SELECT id FROM orgs WHERE personal_of=?", (FID,))
check(PB and docs(PB[0][0]) == [NF], f"P4: her office unchanged {docs(PB[0][0]) if PB else None}")
Fr.delete(B + f"/api/account/import/{iid}")

sys.exit(done("p6577_import_target"))
