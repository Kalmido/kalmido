#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1289.0 (#6576): an import never lets anything of the archive act by itself in the target (the source may still run: a trial
move, both servers in parallel, an import into a test organisation). Invented companies, people and figures only.
 - an organisation with a running invoice series (sent automatically, due today, a "mail still due" mark of the source), the bank
   bookings reminder on and a subscription reminder is exported and imported into an empty organisation: the preview says that
   series and reminders arrive paused; the series arrives off with the reason "import", no mark, no failure count; the result
   warns about the series and every office switch it turned off (payment reminder suggestions, overdue / quotation notices, the
   bank bookings reminder, the subscription reminder); the target's office settings have them off; the watchdog makes no
   invoice and mails nothing there, and it never gives the "an admin is back" task for an imported series
 - a person without an organisation (freelancer) exports her personal office and another one imports it into her private
   workspace: the same (her series paused, nothing made, nothing mailed)
Its own container with the SMTP stub and a watchdog that does not tick by itself (TASKS_WATCHDOG_INTERVAL=3600).
usage: p6576_import_paused_test.py <datadir>"""
# freelancer-matrix: office
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import B, DATA, check, dbx, done, fresh, setup, su_get  # noqa: E402

CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
OFF_API, D, S = "/api/office", "/api/office/docs", "/api/office/series"
TODAY = date.today().isoformat()
KEY = base64.b64encode(os.urandom(32)).decode()
COMPANY = {"name": "Beispiel Film GmbH", "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE", "email": "hallo@beispiel.example",
           "vat_id": "DE123456789", "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}


def tick():
    """One run of the series watchdog in its own process (counts exact, the server's own watchdog does not tick)."""
    r = subprocess.run(["docker", "exec", CT, "python3", "-c", "import app\nfrom kalmido.core.db import connect\nfrom kalmido.office import recurring as x\n"
                        "x._RIN_LAST['at'] = -1e12\nc = connect()\nx.rin_tick(c)\nc.close()\n"], capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr


def mails(to):
    try:
        rows = [json.loads(x) for x in open(os.path.join(DATA, "mail", "out.jsonl"), encoding="utf-8") if x.strip()]
    except FileNotFoundError:
        return []
    return [m for m in rows if to in json.dumps(m["to"])]


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


def run(s, iid, target):
    r = s.post(B + f"/api/account/import/{iid}/run", json={"again": True, "target": target, "people": {}})
    check(r.status_code == 202, f"run starts {r.status_code} {r.text[:200]}")
    j = wait(s, iid)
    check(j.get("state") == "done", f"import into {target} done {j.get('state')} {j.get('error')}")
    return j


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


def warns(j):
    return json.dumps((j.get("result") or {}).get("warnings") or [], ensure_ascii=False)


def office(s, name):
    assert s.put(B + OFF_API + "/settings", json={"lang": "de", "company_fields": {**COMPANY, "name": name}}).ok


def client(s, name, mail):
    r = s.post(B + "/api/clients", json={"name": name, "street": "Marktweg 5", "zip": "50667", "city": "Koeln", "country": "DE", "email_invoice": mail})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def series(s, cl, title):
    r = s.post(B + D, json={"kind": "invoice", "lang": "de", "client_id": cl, "project_title": title + " {month}",
                            "items": [{"title": "Betreuung", "qty": 1, "rate": 500}]})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    r = s.post(B + S, json={"template_id": tid, "every": "monthly", "start": TODAY, "auto_send": 1, "title": title})
    assert r.status_code == 201, r.text
    return r.json()["id"], tid


def rows(oid):
    return dbx("SELECT id, active, pause_why, mail_doc, mail_try, fail_count, next_date FROM office_inv_series WHERE org_id=? ORDER BY id", (oid,))


def made(oid):
    return dbx("SELECT id FROM office_docs WHERE org_id=? AND series_id IS NOT NULL", (oid,))


def back_task(uid):
    return dbx("SELECT id FROM tasks WHERE assignee_id=? AND deleted_at IS NULL AND title LIKE 'Invoice series%paused'", (uid,))


fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_SECRET_KEY": KEY, "KALMIDO_SMTP_HOST": "127.0.0.1", "KALMIDO_SMTP_PORT": "1025",
       "KALMIDO_SMTP_TLS": "none", "KALMIDO_MAIL_FROM": "kalmido@example.test", "TASKS_WATCHDOG_INTERVAL": "3600"})
shutil.copy(os.path.join(N, "stub_mail.py"), DATA)
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/stub_mail.py"])
A = setup()
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Quelle", "admin_id": ALICE}).json()["id"]
ORG_T = A.post(B + "/api/admin/orgs", json={"name": "Ziel", "admin_id": ALICE}).json()["id"]
assert A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG}"}).ok

# ================================================================== the source organisation
office(A, "Quelle GmbH")
CL = client(A, "Muster Medien AG", "rechnung@muster.example")
SID, TID = series(A, CL, "Betreuung")
dbx("UPDATE office_inv_series SET mail_doc=?, mail_try=1, fail_count=2 WHERE id=?", (TID, SID))  # a mark and failures of the source
check(A.put(B + OFF_API + "/bank/noreceipt/reminder", json={"every": "week"}).ok, "the bank bookings reminder is on in the source")
r = A.post(B + OFF_API + "/fixed-costs", json={"label": "Schnittsoftware", "amount": 50, "start": TODAY, "repeat": "yearly", "sub": 1, "notice_days": 30,
                                          "remind_days": 14, "remind_user": ALICE})
check(r.status_code in (200, 201), f"a subscription with its reminder {r.status_code} {r.text[:160]}")
OX, RK = export(A, ORG)
assert A.patch(B + S + f"/{SID}", json={"active": 0}).ok  # the source pauses its own series: whatever is made now is the target's

# ================================================================== into an empty organisation
assert A.patch(B + "/api/settings", json={"workspace": f"org:{ORG_T}"}).ok
iid, pv = opened(A, OX, RK)
check(pv.get("auto_paused") is True, f"the preview says that series and reminders arrive paused {pv.get('auto_paused')}")
j = run(A, iid, ORG_T)
w = warns(j)
check("Invoice series arrive paused" in w, f"the result warns: the series arrive paused {w[:600]}")
for what in ("Payment reminder suggestions", "Notices of overdue invoices", "Notices of expiring quotations", "Reminder of bank bookings without a receipt",
             "Subscription reminders"):
    check(what in w, f"the result names what the import switched off: {what}")
rt = rows(ORG_T)
check(len(rt) == 1 and not rt[0][1] and rt[0][2] == "import" and rt[0][3] is None and rt[0][4] == 0 and rt[0][5] == 0,
      f"the series arrives paused (reason import), no mark, no failures {rt}")
st = A.get(B + OFF_API + "/settings").json()
st = st.get("settings", st)
check(not st.get("dunning_suggest") and not st.get("overdue_notice") and not st.get("offer_exp_notice"),
      f"the target's office switches are off {[st.get(k) for k in ('dunning_suggest', 'overdue_notice', 'offer_exp_notice')]}")
check(A.get(B + OFF_API + "/bank/noreceipt/reminder").json().get("every") == "off", "the bank bookings reminder is off in the target")
check(dbx("SELECT COUNT(*) FROM office_fixed_costs WHERE org_id=? AND remind_user IS NOT NULL", (ORG_T,)) == [(0,)], "the subscription reminder has no person in the target")
n0 = len(mails("rechnung@muster.example"))
tick()
tick()
check(not made(ORG_T) and len(mails("rechnung@muster.example")) == n0, f"the watchdog makes and mails nothing in the target {made(ORG_T)}")
check(not back_task(ALICE), "no 'paused' task for an imported series")
li = A.get(B + S).json().get("items") or []
check([x.get("pause_why") for x in li] == ["import"], f"the series list shows why it is paused {[x.get('pause_why') for x in li]}")

# ================================================================== a freelancer's personal office into another freelancer's private workspace
FID, Fr = freelancer(B, A)
GID, Gr = freelancer(B, A, "greta")
office(Fr, "Frida Schnitt")
CLF = client(Fr, "Studio Kunde", "rechnung@studio.example")
FSID, FTID = series(Fr, CLF, "Frida Schnitt")
dbx("UPDATE office_inv_series SET mail_doc=? WHERE id=?", (FTID, FSID))
PX, PRK = export(Fr, 0)
assert Fr.patch(B + S + f"/{FSID}", json={"active": 0}).ok
iid, pv = opened(Gr, PX, PRK)
check(pv.get("auto_paused") is True, "P4: the preview says it for the personal office too")
j = run(Gr, iid, "private")
check("Invoice series arrive paused" in warns(j), f"P4: the result warns {warns(j)[:400]}")
PB = dbx("SELECT id FROM orgs WHERE personal_of=?", (GID,))
rg = rows(PB[0][0]) if PB else []
check(len(rg) == 1 and not rg[0][1] and rg[0][2] == "import" and rg[0][3] is None, f"P4: her series arrives paused without a mark {rg}")
n0 = len(mails("rechnung@studio.example"))
tick()
check(PB and not made(PB[0][0]) and len(mails("rechnung@studio.example")) == n0 and not back_task(GID), "P4: nothing made, nothing mailed, no task")

sys.exit(done("p6576_import_paused"))
