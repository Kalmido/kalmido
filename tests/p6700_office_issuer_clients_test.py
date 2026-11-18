#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1384.0 API tests (#6700): the clients of an invoice issuer (office/issclients.py) and the hold mark (office/isshold.py).
Own container (start.sh, mode workspaces, KALMIDO_ISSUER_KEYS on, the SMTP stub, a watchdog that does not tick by itself).
Invented companies, people and figures only. tenant-matrix: office  freelancer-matrix: office
In an organisation's office (Alice its admin, Bob the admin of another organisation) and in the personal offices of two
persons without an organisation (Frida, Gina):
 - PUT /api/v1/issuer/clients/by-ref/<ref>: set up 201 (client_new, a hold mark, the history's "create" entry by the issuer),
   GET the fixed list of fields (no note, rate, customer number); unknown field 400 unknown_field; a slash / bad character in the
   ref 400 invalid_field; a key twice in the body 400
 - a change without expect_updated_at 400 version_required (the same body again: 200 unchanged); with it 200; a person's change
   in between 409 conflict with the current client; change and change back within 10 minutes = two history entries
 - text locks: IBAN form in the street / the name 400 invalid_field, a web address in the city 400, an e-mail address in the
   address extra 400; "Booking.com B.V." as name = text_suspicious (201); a person's name alone is fine (no check of names of
   persons); twice "Thomas Müller" = client_lookalike (a mark, no refusal); a person's client with the same VAT ID is never taken over
 - VAT ID: GR... with country GR 400 invalid_field vat_id, EL... fine; DE... with AT 400
 - sight: another issuer's client, a person's client and another person's private client with the same external_ref: 404 / never
   touched (row-level security lets private clients through; the issuer_id filter holds)
 - the hold mark: finalising and sending without the confirmation 409 client_hold (with the mark), with the mark's "at" fine;
   number-preview and recipients name the mark; a person takes it away (an old "at" 409); a new e-mail for invoices by the key
   sets it again and a send again of the finalised invoice needs the confirmation (a reminder and a correction take the same
   two functions, ledger.ofx_finalize and invoices.inv_send)
 - a series with auto_send of a client with a mark: the watchdog's run sends nothing, the invoice stays a draft
 - the portal link to a client with a mark: 409 client_hold
 - merging an issuer's client with a person's client 409, two clients of the same issuer: fine
 - a client in the trash: PUT / GET 409 client_trashed; anonymised: 410 client_gone (a PUT fills nothing in)
 - moving an issuer's client into another workspace: 409
 - day_clients: over the limit 429 limit_reached (a change of an existing client still 200)
 - the office log: issuer_write with the fields old -> new; the alarm "client data" reaches the admins (News)
 - five parallel PUTs of one new external_ref: one client
 - a personal office: the client is the owner's private client (org_id NULL, created_by = owner), she sees it and takes its mark away
usage: p6700_office_issuer_clients_test.py <datadir>"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check  # noqa: E402
import dbx as dbxm  # noqa: E402
from freelancer_fixture import FEATURES, PASSWORD, freelancer, login  # noqa: E402

kt.docker_logs_on_first_fail()
DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
OF = "/api/office"
D = OF + "/docs"
V = B + "/api/v1"
CR = "/issuer/clients/by-ref/"
TODAY = __import__("datetime").date.today().isoformat()
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "phone": "+49 40 1234567", "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001"}
# the issuer functions of office/issuers.py ISS_REUSED this suite runs with the issuer's context (the PUT / GET below)
REUSED_HERE = ("team.clients.clean_client", "office.owrite.ow_write", "office.owrite.ow_created")


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


def kput(key, ref, b, raw=None):
    if raw is not None:
        return requests.put(V + CR + ref, headers={**hk(key), "Content-Type": "application/json"}, data=raw, timeout=30)
    return requests.put(V + CR + ref, headers=hk(key), json=b, timeout=30)


def kget(key, ref):
    return requests.get(V + CR + ref, headers=hk(key), timeout=30)


def code(r):
    try:
        e = r.json().get("error")
        return e.get("code") if isinstance(e, dict) else None
    except ValueError:
        return None


def field(r):
    try:
        return (r.json().get("error") or {}).get("field")
    except (ValueError, AttributeError):
        return None


def news(uid, what):
    return sql("SELECT data FROM notifications WHERE user_id=? AND kind='integfail' AND data->>'what'=?", (uid, what))


def mails(to):
    try:
        rows = [json.loads(x) for x in open(os.path.join(DATA, "mail", "out.jsonl"), encoding="utf-8") if x.strip()]
    except FileNotFoundError:
        return []
    return [m for m in rows if to in json.dumps(m["to"])]


def in_ct(code_):
    r = subprocess.run(["docker", "exec", kt.CT, "python3", "-c", code_], capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def setup_area(S, code_):
    assert S.put(B + OF + "/settings", json={"lang": "de", "company_fields": COMPANY}).ok
    r = S.post(B + OF + "/num-ranges", json={"code": code_, "scheme": code_ + "-{yyyy}-{seq:03}"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def issuer(S, rg, name):
    r = S.post(B + OF + "/issuers", json={"name": name, "range_id": rg, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()["issuer"]["id"], r.json()["key"]


def draft(S, cid):
    r = S.post(B + D, json={"kind": "invoice", "lang": "de", "client_id": cid, "project_title": "Schnitt", "service_from": TODAY,
                            "service_to": TODAY, "items": [{"title": "Schnitt", "qty": 1, "rate": 400}]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


ADDR = {"street": "Marktweg 5", "zip": "50667", "city": "Köln", "country": "DE"}

# ---------------------------------------------------------------- the container
kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ISSUER_KEYS": "1", "KALMIDO_SMTP_HOST": "127.0.0.1", "KALMIDO_SMTP_PORT": "1025",
          "KALMIDO_SMTP_TLS": "none", "KALMIDO_MAIL_FROM": "kalmido@example.test", "TASKS_WATCHDOG_INTERVAL": "3600"}, data=DATA)
shutil.copy(os.path.join(N, "stub_mail.py"), DATA)
subprocess.run(["docker", "exec", "-d", kt.CT, "python", "/data/stub_mail.py"])
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob Other", "password": PASSWORD, "email": "bob@example.com"})
assert r.ok, r.text
BOB = r.json()["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
ORG2 = A.post(B + "/api/admin/orgs", json={"name": "Gamma", "admin_id": ALICE}).json()["id"]
ORGB = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": BOB}).json()["id"]
assert A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"}).ok
Bo = login(B, "bob")
Bo.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORGB}"})
FID, Fr = freelancer(B, A)
GID, Gi = freelancer(B, A, "gina")
for S in (Fr, Gi):
    S.patch(B + "/api/settings", json={"workspace": "private"})

RG = setup_area(A, "GT")
IID, KEY = issuer(A, RG, "Shop")
IID2, KEY2 = issuer(A, RG, "Booking")
IID3, KEY3 = issuer(A, RG, "Text")  # its own key for the text checks (each key may make 60 calls a minute)
setup_area(Bo, "BT")
FRG = setup_area(Fr, "WEB")
FI, FK = issuer(Fr, FRG, "Own script")
GRG = setup_area(Gi, "GIN")
GI, GK = issuer(Gi, GRG, "Gina script")

# ---------------------------------------------------------------- set up, read, fixed fields
r = kput(KEY, "prod:account:12", {"name": "Musterkunde GmbH", **ADDR, "email_invoice": "rechnung@muster.example", "buyer_reference": "991-12345-67"})
check(r.status_code == 201 and "client_new" in (r.json().get("flags") or []) and r.json().get("checked") is False,
      f"set up: 201, client_new, not checked {r.status_code} {r.text[:200]}")
C1 = sql("SELECT id, org_id, created_by, issuer_id, external_ref, issuer_hold, customer_no FROM clients WHERE external_ref='prod:account:12'")
check(len(C1) == 1 and C1[0][1] == ORG and C1[0][2] is None and C1[0][3] == IID and C1[0][5] and not (C1[0][6] or ""),
      f"the client: the organisation's, the issuer's, a mark, no customer number {C1}")
CID = C1[0][0] if C1 else 0
U1 = r.json().get("updated_at")
r = kget(KEY, "prod:account:12")
j = r.json() if r.ok else {}
check(r.ok and j.get("name") == "Musterkunde GmbH" and j.get("city") == "Köln" and not {"note", "rate", "customer_no", "id", "contact", "org_id"} & set(j),
      f"GET: the fixed list of fields {sorted(j)}")
check(kget(KEY, "prod:account:99").status_code == 404, "an unknown ref 404")
r = kput(KEY, "x", {"name": "Kunde", "note": "Hallo"})
check(r.status_code == 400 and code(r) == "unknown_field" and not sql("SELECT 1 FROM clients WHERE external_ref='x'"), f"an unknown field 400 unknown_field {r.text[:160]}")
r = kput(KEY, "a/b", {"name": "Kunde"})
check(r.status_code == 400 and field(r) == "external_ref", f"a slash in the ref 400 invalid_field {r.status_code} {r.text[:160]}")
r = kput(KEY, "a b", {"name": "Kunde"})
check(r.status_code == 400 and field(r) == "external_ref", f"a space in the ref 400 {r.status_code}")
r = kput(KEY, "y", None, raw='{"name": "Kunde", "name": "Andere"}')
check(r.status_code == 400 and not sql("SELECT 1 FROM clients WHERE external_ref='y'"), f"a key twice 400 {r.status_code}")
r = kput(KEY, "y2", {"name": "Kunde", "customer_no": "K-1"})
check(r.status_code == 400 and code(r) == "unknown_field", "customer_no is no field of the key (stays empty)")
hist = A.get(B + f"/api/clients/{CID}/history").json().get("items") or []
check(any(h["action"] == "create" and h.get("issuer") and "Shop" in (h.get("name") or "") for h in hist), f"the history: created by the issuer Shop {hist}")
lg = A.get(B + f"/api/office/issuers/{IID}/log").json().get("log") or []
check(any(x["action"] == "issuer_write" for x in lg), f"the office log: issuer_write {[x['action'] for x in lg]}")
check(bool(news(ALICE, "issuer_client")), "the alarm 'client data' reaches the organisation's admin")
src = open(os.path.join(N, "..", "kalmido", "office", "issuers.py"), encoding="utf-8").read()
m = re.search(r"ISS_REUSED = \(([^)]*)\)", src)
check(m and set(REUSED_HERE) <= set(re.findall(r'"([^"]+)"', m.group(1))), "ISS_REUSED names the clients' functions this suite runs with the issuer")

# ---------------------------------------------------------------- the version, conflicts, the history without merging
r = kput(KEY, "prod:account:12", {"city": "Bonn"})
check(r.status_code == 400 and code(r) == "version_required", f"a change without expect_updated_at 400 version_required {r.text[:160]}")
r = kput(KEY, "prod:account:12", {"name": "Musterkunde GmbH", "city": "Köln"})
check(r.status_code == 200, f"the same values again without the version: 200 (a queue's retry) {r.status_code} {r.text[:160]}")
r = kput(KEY, "prod:account:12", {"city": "Bonn", "expect_updated_at": U1})
check(r.ok and r.json().get("city") == "Bonn", f"a change with the version 200 {r.status_code} {r.text[:160]}")
U2 = r.json().get("updated_at") if r.ok else ""
r = kput(KEY, "prod:account:12", {"city": "Köln", "expect_updated_at": U2})
check(r.ok and r.json().get("city") == "Köln", f"and back {r.status_code}")
U3 = r.json().get("updated_at") if r.ok else ""
n = sql("SELECT COUNT(*) FROM obj_history WHERE kind='client' AND ref_id=? AND action='update' AND via=?", (CID, f"issuer:{IID}"))[0][0]
check(n == 2, f"change and change back within 10 minutes: two history entries, never merged {n}")
lg = sql("SELECT detail FROM office_doc_log WHERE issuer_id=? AND action='issuer_write' ORDER BY id DESC LIMIT 1", (IID,))
check(lg and "Bonn" in str(lg[0][0]) and "Köln" in str(lg[0][0]), f"the log line holds the field old -> new {lg}")
r = A.patch(B + f"/api/clients/{CID}", json={"phone": "+49 221 1234567"})
check(r.ok, f"a person changes the client {r.status_code}")
r = kput(KEY, "prod:account:12", {"zip": "50668", "expect_updated_at": U3})
check(r.status_code == 409 and code(r) == "conflict" and (r.json()["error"].get("current") or {}).get("zip") == "50667"
      and sql("SELECT zip FROM clients WHERE id=?", (CID,))[0][0] == "50667", f"a person's change in between: 409 with the current client {r.text[:200]}")

# ---------------------------------------------------------------- text locks, names, look-alikes, VAT IDs
r = kput(KEY3, "t1", {"name": "Kunde Eins", **ADDR, "street": "Zahle an DE89 3704 0044 0532 0130 00"})
check(r.status_code == 400 and field(r) == "street" and not sql("SELECT 1 FROM clients WHERE external_ref='t1'"), f"an IBAN in the street 400 {r.text[:160]}")
r = kput(KEY3, "t1", {"name": "DE89370400440532013000 GmbH"})
check(r.status_code == 400 and field(r) == "name", f"an IBAN in the name 400 {r.status_code}")
r = kput(KEY3, "t1", {"name": "Kunde Eins", **ADDR, "city": "www.example.com"})
check(r.status_code == 400 and field(r) == "city", f"a web address in the city 400 {r.status_code}")
r = kput(KEY3, "t1", {"name": "Kunde Eins", **ADDR, "address_extra": "Post an zahlung@example.com"})
check(r.status_code == 400 and field(r) == "address_extra", f"an e-mail address in the address extra 400 {r.status_code}")
r = kput(KEY3, "t1", {"name": "Kunde Eins", **ADDR, "city": "St.Gallen", "country": "CH"})
check(r.status_code == 201, f"St.Gallen is no web address {r.status_code} {r.text[:160]}")
r = kput(KEY3, "t2", {"name": "Booking.com B.V.", **ADDR})
check(r.status_code == 201 and "text_suspicious" in r.json().get("flags", []), f"a web pattern in the name: text_suspicious, no refusal {r.text[:200]}")
r = kput(KEY3, "t3", {"name": "Thomas Müller", **ADDR})
check(r.status_code == 201 and "client_lookalike" not in r.json().get("flags", []), f"a person's name alone: set up, no check of names of persons {r.text[:200]}")
r = kput(KEY3, "t4", {"name": "Thomas  Müller", **ADDR})
check(r.status_code == 201 and "client_lookalike" in r.json().get("flags", []), f"twice 'Thomas Müller': client_lookalike, no refusal {r.text[:200]}")
HAND = A.post(B + "/api/clients", json={"name": "Echtkunde AG", **ADDR, "vat_id": "DE811111111", "email_invoice": "buchhaltung@echt.example"}).json()["id"]
r = kput(KEY3, "t5", {"name": "Echtkunde AG", **ADDR, "vat_id": "DE811111111", "email_invoice": "dieb@falsch.example"})
check(r.status_code == 201 and "client_lookalike" in r.json().get("flags", []), f"a person's client with the same name / VAT ID: a new client, lookalike {r.text[:200]}")
hand = sql("SELECT email_invoice, issuer_id, external_ref FROM clients WHERE id=?", (HAND,))[0]
check(hand[0] == "buchhaltung@echt.example" and hand[1] is None and hand[2] is None, f"the person's client is never taken over {hand}")
r = kput(KEY3, "v1", {"name": "Kreta Reisen", **ADDR, "country": "GR", "vat_id": "GR123456789"})
check(r.status_code == 400 and field(r) == "vat_id", f"GR... with country GR 400 invalid_field vat_id {r.text[:200]}")
r = kput(KEY3, "v1", {"name": "Kreta Reisen", **ADDR, "country": "GR", "vat_id": "EL123456789"})
check(r.status_code == 201, f"EL... with GR fine {r.status_code} {r.text[:160]}")
r = kput(KEY3, "v2", {"name": "Wien Film", **ADDR, "country": "AT", "vat_id": "DE123456789"})
check(r.status_code == 400 and field(r) == "vat_id", f"DE... with AT 400 {r.status_code}")
r = kput(KEY3, "v3", {"name": "Ohne USt", **ADDR})
check(r.status_code == 201, "a German buyer without a VAT ID is fine")

# ---------------------------------------------------------------- sight
check(kget(KEY2, "prod:account:12").status_code == 404, "another issuer of the same office: 404 on the first one's client")
r = requests.put(V + f"/issuer/clients/by-ref/{'konto:1'}", headers=hk(GK), json={"name": "Ginas Kundin", **ADDR})  # tenant: PUT /api/v1/issuer/clients/by-ref/{}
check(r.status_code == 201, f"Gina's issuer sets up konto:1 in her private office {r.status_code} {r.text[:160]}")
check(requests.get(V + f"/issuer/clients/by-ref/{'konto:1'}", headers=hk(FK)).status_code == 404,  # tenant: GET /api/v1/issuer/clients/by-ref/{}
      "another person's private client with the same external_ref: 404 for Frida's key")
r = requests.put(V + f"/issuer/clients/by-ref/{'konto:1'}", headers=hk(FK), json={"name": "Fridas Kundin", **ADDR, "email_invoice": "kundin@frida.example"})
check(r.status_code == 201 and sql("SELECT name FROM clients WHERE issuer_id=? AND external_ref='konto:1'", (GI,))[0][0] == "Ginas Kundin",
      f"Frida's key sets up its own konto:1, Gina's stays as it is {r.status_code}")
FCL = sql("SELECT id, org_id, created_by FROM clients WHERE issuer_id=? AND external_ref='konto:1'", (FI,))
check(FCL and FCL[0][1] is None and FCL[0][2] == FID, f"private office: the owner's private client (org_id NULL, created_by = owner) {FCL}")
FCID = FCL[0][0] if FCL else 0
check(any(x["id"] == FCID for x in Fr.get(B + "/api/clients").json().get("clients") or []), "Frida sees it in her clients")
check(not any(x["id"] == FCID for x in Gi.get(B + "/api/clients").json().get("clients") or []), "Gina does not")
check(bool(news(FID, "issuer_client")), "private office: the alarm reaches the owner")
check(Bo.post(B + f"/api/clients/{CID}/issuer-hold", json={"at": "x"}).status_code == 404, "another organisation's admin: 404 on the mark")

# ---------------------------------------------------------------- the hold mark: finalising and sending ask for the confirmation
DOC = draft(A, CID)
pv = A.get(B + f"{D}/{DOC}/number-preview").json()
hold = pv.get("client_hold") or {}
check(hold.get("at") and hold.get("new") and hold.get("issuer") == "Shop" and any(f["field"] == "email_invoice" for f in hold.get("fields") or []),
      f"number-preview names the mark {hold}")
r = A.post(B + f"{D}/{DOC}/finalize", json={})
check(r.status_code == 409 and (r.json().get("client_hold") or {}).get("at") == hold.get("at")
      and not sql("SELECT locked_at FROM office_docs WHERE id=?", (DOC,))[0][0], f"finalise without the confirmation: 409 client_hold {r.text[:200]}")
r = A.post(B + f"{D}/{DOC}/finalize", json={"client_hold_ok": "2020-01-01T00:00:00Z"})
check(r.status_code == 409, f"an old / wrong confirmation: 409 {r.status_code}")
r = A.post(B + f"{D}/{DOC}/finalize", json={"client_hold_ok": hold.get("at")})
check(r.ok and r.json().get("number"), f"finalised with the confirmation {r.status_code} {r.text[:200]}")
rc = A.get(B + f"{D}/{DOC}/recipients").json()
check((rc.get("client_hold") or {}).get("at") == hold.get("at") and rc.get("to") == "rechnung@muster.example", f"recipients name the mark {rc}")
r = A.post(B + f"{D}/{DOC}/send", json={"to": "rechnung@muster.example"})
check(r.status_code == 409 and not mails("rechnung@muster.example"), f"send without the confirmation: 409, no mail {r.status_code} {r.text[:160]}")
r = A.post(B + f"{D}/{DOC}/send", json={"to": "rechnung@muster.example", "client_hold_ok": hold.get("at")})
check(r.ok and kt.until(lambda: mails("rechnung@muster.example"), timeout=20), f"sent with the confirmation {r.status_code} {r.text[:200]}")
r = A.post(B + f"/api/clients/{CID}/issuer-hold", json={"at": "2020-01-01T00:00:00Z"})
check(r.status_code == 409 and sql("SELECT issuer_hold FROM clients WHERE id=?", (CID,))[0][0], "an old mark is not taken away (409)")
r = A.post(B + f"/api/clients/{CID}/issuer-hold", json={"at": hold.get("at")})
check(r.ok and not sql("SELECT issuer_hold FROM clients WHERE id=?", (CID,))[0][0], f"a person takes the mark away {r.status_code} {r.text[:160]}")
check(kget(KEY, "prod:account:12").json().get("checked") is True, "the key sees: checked")
check(not (A.get(B + f"/api/clients/{CID}").json().get("issuer") or {}).get("client_hold"), "the client card: no mark any more")
check(any(x["action"] == "issuer_hold_checked" and x["by"] == "person" for x in A.get(B + f"/api/office/issuers/{IID}/log").json().get("log") or []),
      "the office log: checked by a person")
# the key changes the e-mail for invoices: the mark is back, a send again of the finalised invoice asks again
cur = kget(KEY, "prod:account:12").json()
r = kput(KEY, "prod:account:12", {"email_invoice": "neu@umleitung.example", "expect_updated_at": cur["updated_at"]})
check(r.ok and r.json().get("checked") is False and "client_new" not in r.json().get("flags", []), f"a new e-mail for invoices sets the mark again {r.text[:200]}")
card = A.get(B + f"/api/clients/{CID}").json().get("issuer") or {}
h2 = card.get("client_hold") or {}
check(any(f["field"] == "email_invoice" and f["old"] == "rechnung@muster.example" and f["new"] == "neu@umleitung.example" for f in h2.get("fields") or []),
      f"the client card shows the mark old -> new {h2}")
r = A.post(B + f"{D}/{DOC}/send", json={"to": "neu@umleitung.example"})
check(r.status_code == 409 and not mails("neu@umleitung.example"), f"send again after the changed e-mail: 409 without the confirmation {r.status_code}")
r = A.post(B + f"{D}/{DOC}/send", json={"to": "neu@umleitung.example", "client_hold_ok": h2.get("at")})
check(r.ok, f"send again with the confirmation {r.status_code} {r.text[:160]}")
r = A.post(B + OF + f"/clients/{CID}/portal-link", json={})
check(r.status_code == 409 and r.json().get("client_hold"), f"the portal link to a client with a mark: 409 {r.status_code} {r.text[:160]}")

# ---------------------------------------------------------------- a series with auto_send: nothing goes out while the mark stands
r = kput(KEY, "abo:1", {"name": "Abo Kundin", **ADDR, "email_invoice": "serie@umleitung.example"})
assert r.status_code == 201, r.text
CS = sql("SELECT id FROM clients WHERE external_ref='abo:1' AND issuer_id=?", (IID,))[0][0]
TPL = draft(A, CS)
r = A.post(B + OF + "/series", json={"template_id": TPL, "every": "monthly", "start": TODAY, "auto_send": 1, "title": "Abo"})
check(r.status_code == 201, f"a series with auto_send {r.status_code} {r.text[:160]}")
SID = r.json()["id"] if r.status_code == 201 else 0
in_ct("import app\nfrom kalmido.core.db import connect\nfrom kalmido.office import recurring as x\nx._RIN_LAST['at'] = -1e12\nc = connect()\nx.rin_tick(c)\nc.close()\n")
made = sql("SELECT id, number, status, locked_at FROM office_docs WHERE series_id=? ORDER BY id", (SID,))
check(made and not made[-1][3] and not made[-1][1] and not mails("serie@umleitung.example"),
      f"auto_send with a mark: no mail, the invoice stays a draft {made}")

# ---------------------------------------------------------------- merging, moving, trash, anonymised
r = A.post(B + "/api/clients/merge", json={"target": HAND, "ids": [HAND, CID]})
check(r.status_code == 409 and sql("SELECT 1 FROM clients WHERE id=?", (CID,)), f"merging an issuer's client with a person's client: 409 {r.status_code} {r.text[:160]}")
r = A.post(B + "/api/clients/merge", json={"target": HAND, "ids": [HAND, CID], "dry": True})
check(r.status_code == 409, "also the overview (dry) 409")
T3 = sql("SELECT id FROM clients WHERE external_ref='t3' AND issuer_id=?", (IID3,))[0][0]
T4 = sql("SELECT id FROM clients WHERE external_ref='t4' AND issuer_id=?", (IID3,))[0][0]
r = A.post(B + "/api/clients/merge", json={"target": T3, "ids": [T3, T4]})
check(r.ok and sql("SELECT issuer_hold FROM clients WHERE id=?", (T3,))[0][0], f"two clients of the same issuer merge; the mark stays {r.status_code} {r.text[:160]}")
r = kget(KEY3, "t4")
check(r.status_code == 410 and code(r) == "client_gone", f"the merged-away ref: 410 client_gone {r.status_code}")
r = A.patch(B + f"/api/clients/{T3}", json={"org_id": ORG2})  # T3 has no finalised document (they would hold it anyway)
check(r.status_code == 409 and "invoice issuer" in r.text and sql("SELECT org_id FROM clients WHERE id=?", (T3,))[0][0] == ORG,
      f"moving an issuer's client into another workspace: 409 {r.status_code} {r.text[:160]}")
T2 = sql("SELECT id FROM clients WHERE external_ref='t2' AND issuer_id=?", (IID3,))[0][0]
r = A.delete(B + f"/api/clients/{T2}")
check(r.ok and r.json().get("trashed"), f"the client into the trash {r.text[:160]}")
cur_t2 = sql("SELECT updated_at FROM clients WHERE id=?", (T2,))[0][0]
r = kput(KEY3, "t2", {"city": "Bonn", "expect_updated_at": str(cur_t2)})
check(r.status_code == 409 and code(r) == "client_trashed" and sql("SELECT city FROM clients WHERE id=?", (T2,))[0][0] == "Köln", f"PUT on a client in the trash: 409 client_trashed {r.text[:160]}")
check(code(kget(KEY3, "t2")) == "client_trashed", "GET: 409 client_trashed")
T1 = sql("SELECT id FROM clients WHERE external_ref='t1' AND issuer_id=?", (IID3,))[0][0]
r = A.post(B + f"/api/clients/{T1}/anonymize")
check(r.ok, f"anonymise {r.status_code} {r.text[:160]}")
r = kput(KEY3, "t1", {"name": "Kunde Eins", **ADDR})
check(r.status_code == 410 and code(r) == "client_gone" and sql("SELECT street FROM clients WHERE id=?", (T1,))[0][0] == "", f"PUT on an anonymised client: 410, nothing filled in {r.text[:160]}")
check(kget(KEY3, "t1").status_code == 410, "GET: 410")

# ---------------------------------------------------------------- the limit of new clients, parallel set-ups
assert A.patch(B + OF + f"/issuers/{IID2}", json={"limits": {"day_clients": 1}}).ok
r = kput(KEY2, "b1", {"name": "Erster", **ADDR})
check(r.status_code == 201, f"the first client within the limit {r.status_code}")
r = kput(KEY2, "b2", {"name": "Zweiter", **ADDR})
check(r.status_code == 429 and code(r) == "limit_reached" and r.headers.get("Retry-After") and not sql("SELECT 1 FROM clients WHERE external_ref='b2'"),
      f"over day_clients: 429 limit_reached {r.status_code} {r.text[:160]}")
cur = kget(KEY2, "b1").json()
check(kput(KEY2, "b1", {"zip": "50668", "expect_updated_at": cur["updated_at"]}).ok, "a change of an existing client still 200 at the limit")
check(not sql("SELECT paused FROM office_issuers WHERE id=?", (IID2,))[0][0] and bool(news(ALICE, "issuer_limit")), "the limit pauses nothing, the admins hear of it")
assert A.patch(B + OF + f"/issuers/{IID2}", json={"limits": {"day_clients": 0}}).ok  # lowering is free; raising asks for the password
codes = []


def one():
    codes.append(kput(KEY, "par:1", {"name": "Parallel GmbH", **ADDR}).status_code)


ts = [threading.Thread(target=one) for _ in range(5)]
for t in ts:
    t.start()
for t in ts:
    t.join()
n = sql("SELECT COUNT(*) FROM clients WHERE issuer_id=? AND external_ref='par:1'", (IID,))[0][0]
check(n == 1 and codes.count(201) == 1 and all(x in (200, 201) for x in codes), f"five parallel set-ups of one ref: one client {codes} {n}")

# ---------------------------------------------------------------- the personal office: its owner checks and sends
FDOC = draft(Fr, FCID)
r = Fr.post(B + f"{D}/{FDOC}/finalize", json={})
check(r.status_code == 409 and r.json().get("client_hold"), f"private office: finalising asks for the confirmation {r.status_code}")
fh = Fr.get(B + f"/api/clients/{FCID}").json().get("issuer", {}).get("client_hold") or {}
r = Fr.post(B + f"/api/clients/{FCID}/issuer-hold", json={"at": fh.get("at")})
check(r.ok, f"private office: the owner takes the mark away {r.status_code} {r.text[:160]}")
r = Fr.post(B + f"{D}/{FDOC}/finalize", json={})
check(r.ok, f"private office: finalised after the check without a confirmation {r.status_code} {r.text[:160]}")

sys.exit(kt.done("p6700_office_issuer_clients"))
