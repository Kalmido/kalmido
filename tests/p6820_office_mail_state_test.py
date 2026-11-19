#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1435.0 API tests (#6820): the delivery state of a document's e-mail (office/mailstate.py). Own container (start.sh through
kt.fresh, SMTP to the stub of tests/stub_mail.py, which refuses the recipient refuse@...). Invented companies, people and
figures only. tenant-matrix: office  freelancer-matrix: office
In an organisation's office (Alice its admin) and in the personal office of a person without an organisation (Frida):
 - a mail the server takes: mail {state: sent, at}; a history entry of the core (obj_history, kind office_doc, action mail,
   actor the system: user none, via system)
 - a mail the server refuses (550): 409, the document stays unsent (status issued, no sent_at), mail.state failed (committed
   though the request failed), the office log line mail_failed, the history entry
 - "Delivery failed" (POST .../mail-bounced): bounced, the history entry with the person, the office log line mail_bounced;
   {bounced: false} = sent again; a second false 409; a document never mailed (a draft, the refused one) 409
 - the list: every row carries mail; ?status=mail_failed = the failed and the bounced ones (also quotations)
 - a copy starts with none; a quotation mailed and marked works the same (any document kind)
 - a read-only member: 403; another organisation's document: 404
 - the answers carry no columns mail_state / mail_at (only mail {state, at})
usage: p6820_office_mail_state_test.py <datadir>"""
import json
import os
import shutil
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, CT, DATA, check, dbx, sess  # noqa: E402
from freelancer_fixture import FEATURES, freelancer  # noqa: E402

OF = "/api/office"
D = OF + "/docs"
COMPANY = {"name": "Beispiel Film GmbH", "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE", "email": "hallo@beispiel.example",
           "vat_id": "DE123456789", "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}

kt.fresh(env={"KALMIDO_SMTP_HOST": "127.0.0.1", "KALMIDO_SMTP_PORT": "1025", "KALMIDO_SMTP_TLS": "none",
              "KALMIDO_MAIL_FROM": "kalmido@example.test", "KALMIDO_INSTANCE_MODE": "workspaces"}, prefix="P6820")
os.makedirs(os.path.join(DATA, "mail", "in"), exist_ok=True)
shutil.copy(os.path.join(N, "stub_mail.py"), DATA)
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/stub_mail.py"], check=True)
kt.until(lambda: subprocess.run(["docker", "exec", CT, "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 1025), 1)"],
                                capture_output=True).returncode == 0, 20)

A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ids = {}
for u in ("rita", "carol"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": "password123", "email": f"{u}@example.com", "orgs": []})
    assert r.ok, r.text
    ids[u] = r.json()["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
BETA = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": ids["carol"]}).json()["id"]
assert A.put(B + f"/api/orgs/{ORG}/members", json={"email": "rita@example.com", "role": "readonly"}).ok
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
Ro, Ca = sess("rita"), sess("carol")
for s, o in ((Ro, ORG), (Ca, BETA)):
    s.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{o}"})
FID, Fr = freelancer(B, A)
Fr.patch(B + "/api/settings", json={"workspace": "private"})


def hist(did):
    return dbx("SELECT user_id, via, action, vals_before::text, vals_after::text FROM obj_history WHERE kind='office_doc' AND ref_id=? AND action='mail' ORDER BY id", (did,))


def state(after):
    return json.loads(after).get("mail_state")


def run(s, who, uid, ro=None, other=None):
    def ok(cond, what):
        check(cond, f"{who}: {what}")

    assert s.put(B + OF + "/settings", json={"company_fields": COMPANY}).ok
    r = s.post(B + "/api/clients", json={"name": f"Kunde {who} GmbH", "street": "Weg 2", "zip": "10115", "city": "Berlin", "country": "DE",
                                         "email": f"kunde-{who}@example.com"})
    assert r.ok, r.text
    CL = r.json()["id"]

    def doc(kind="invoice"):
        r = s.post(B + D, json={"kind": kind, "client_id": CL, "service_from": kt.today().isoformat(), "items": [{"title": "Schnitt", "qty": 1, "rate": 100}]})
        assert r.status_code == 201, r.text
        did = r.json()["id"]
        assert s.post(B + f"{D}/{did}/finalize").ok
        return did

    # ---- the server takes it
    I1 = doc()
    ok(s.get(B + f"{D}/{I1}").json().get("mail") == {"state": "none", "at": None}, "a finalised invoice not mailed: none")
    r = s.post(B + f"{D}/{I1}/send", json={"to": "kunde@example.com"})
    d = s.get(B + f"{D}/{I1}").json()
    ok(r.ok and d["status"] == "sent" and (d.get("mail") or {}).get("state") == "sent" and d["mail"].get("at"), f"sent: mail {d.get('mail')} {r.status_code} {r.text[:160]}")
    ok("mail_state" not in d and "mail_at" not in d, "the answer: only mail {state, at}, not the columns")
    h = hist(I1)
    ok(len(h) == 1 and h[0][0] is None and h[0][1] == "system" and state(h[0][3]) == "none" and state(h[0][4]) == "sent",
       f"the history: none -> sent by the system {h}")
    # ---- the server refuses it
    I2 = doc()
    r = s.post(B + f"{D}/{I2}/send", json={"to": "refuse@example.com"})
    d = s.get(B + f"{D}/{I2}").json()
    ok(r.status_code == 409 and d["status"] == "issued" and not d.get("sent_at") and (d.get("mail") or {}).get("state") == "failed",
       f"refused: 409, not sent, mail failed {r.status_code} {d.get('status')} {d.get('sent_at')} {d.get('mail')}")
    h = hist(I2)
    ok([(x[0], x[1], state(x[4])) for x in h] == [(None, "system", "failed")], f"the history: failed by the system {h}")
    lg = s.get(B + f"{D}/{I2}/log").json().get("log") or []
    ok(any(x.get("action") == "mail_failed" for x in lg) and not any(x.get("action") == "send" for x in lg), f"the office log: mail_failed, no send {[x.get('action') for x in lg]}")
    ok("refuse@example.com" not in json.dumps(d.get("mail")), "the state carries no address")
    # ---- a person marks a bounce
    D0 = s.post(B + D, json={"kind": "invoice", "client_id": CL, "items": [{"title": "Entwurf", "qty": 1, "rate": 10}]}).json()["id"]
    ok(s.post(B + f"{D}/{D0}/mail-bounced", json={}).status_code == 409, "a draft never mailed: 409")
    ok(s.post(B + f"{D}/{I2}/mail-bounced", json={}).status_code == 409, "the refused one (never went out): 409")
    r = s.post(B + f"{D}/{I1}/mail-bounced", json={})
    ok(r.ok and (r.json().get("mail") or {}).get("state") == "bounced", f"Delivery failed: bounced {r.status_code} {r.text[:200]}")
    h = hist(I1)
    ok(len(h) == 2 and h[1][0] == uid and h[1][1] is None and state(h[1][4]) == "bounced", f"the history: bounced by the person {h}")
    lg = s.get(B + f"{D}/{I1}/log").json().get("log") or []
    ok(any(x.get("action") == "mail_bounced" for x in lg), f"the office log: mail_bounced {[x.get('action') for x in lg]}")
    # ---- the list and its filter
    rows = s.get(B + D + "?kind=invoice").json()
    rows = rows.get("docs") if isinstance(rows, dict) else rows
    by = {x["id"]: x for x in rows or []}
    ok(by.get(I1, {}).get("mail", {}).get("state") == "bounced" and by.get(D0, {}).get("mail") == {"state": "none", "at": None},
       f"the list rows carry mail {by.get(I1, {}).get('mail')} {by.get(D0, {}).get('mail')}")
    rows = s.get(B + D + "?kind=invoice&status=mail_failed").json()
    got = {x["id"] for x in (rows.get("docs") if isinstance(rows, dict) else rows) or []}
    ok(got == {I1, I2}, f"the filter Delivery failed: the bounced and the refused one {sorted(got)} {I1} {I2}")
    # ---- back, and once more
    r = s.post(B + f"{D}/{I1}/mail-bounced", json={"bounced": False})
    ok(r.ok and r.json()["mail"]["state"] == "sent", f"Delivered after all: sent {r.status_code} {r.text[:160]}")
    ok(s.post(B + f"{D}/{I1}/mail-bounced", json={"bounced": False}).status_code == 409, "not marked: 409")
    ok(len(hist(I1)) == 3, "the way back is an entry too")
    # ---- a copy, a quotation
    r = s.post(B + f"{D}/{I1}/duplicate", json={})
    ok(r.ok and r.json().get("mail") == {"state": "none", "at": None}, f"a copy starts with none {r.status_code} {r.json().get('mail') if r.ok else r.text[:160]}")
    Q = doc("offer")
    r = s.post(B + f"{D}/{Q}/send", json={"to": "kunde@example.com"})
    ok(r.ok and s.post(B + f"{D}/{Q}/mail-bounced", json={}).ok, f"a quotation: mailed and marked {r.status_code} {r.text[:160]}")
    rows = s.get(B + D + "?kind=offer&status=mail_failed").json()
    ok({x["id"] for x in (rows.get("docs") if isinstance(rows, dict) else rows) or []} == {Q}, "the quotations' filter")
    # ---- others
    if ro is not None:
        r = ro.post(B + f"{D}/{Q}/mail-bounced", json={"bounced": False})
        ok(r.status_code == 403 and s.get(B + f"{D}/{Q}").json()["mail"]["state"] == "bounced", f"a read-only member: 403 {r.status_code}")
    if other is not None:  # tenant: POST /api/office/docs/{}/mail-bounced
        ok(other.post(B + f"/api/office/docs/{I1}/mail-bounced", json={}).status_code == 404, "another organisation's document: 404")


run(A, "org", ALICE, ro=Ro, other=Ca)
run(Fr, "freelancer", FID, other=Ca)
r = Fr.post(B + f"{D}/1/mail-bounced", json={})
check(r.status_code == 404, f"the freelancer: the organisation's first document 404 {r.status_code}")
sys.exit(kt.done("p6820_office_mail_state"))
