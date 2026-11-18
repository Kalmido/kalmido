#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1365.0 (#6698): additional number ranges through the organisation export and import (admin/orgexport.py
office/num_ranges.json, admin/oi_office.py _p_num_range / _p_numbers). Own container (start.sh, KALMIDO_SECRET_KEY).
Invented names and figures only.
tenant-matrix: own  freelancer-matrix: office
 - an organisation with the range GT, two finalised invoices in it and one in the main range: exported, imported into an
   empty organisation: the range comes along with a new id, its documents point at it, its counter (office_numbers kind
   r<new id>) continues (the next GT invoice is the third), its hash chain is its own and intact
 - a person without an organisation who has a range GT already imports the same export privately: the imported range gets
   another code (GT2, named in the report), both ranges count apart
 - Fable F3: the import checks a range like the route does: an organisation whose own range already holds the archive's scheme
   takes the range closed (a warning names it), its documents stay in that range (never the main range), no new invoice there;
   2.1399.0 (#7037, F1): it opens again only with a scheme the office accepts
usage: p6698_b_office_numranges_import_test.py <datadir>"""
import base64
import os
import subprocess
import sys
import time

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess, su_get, until  # noqa: E402
from testclock import today  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
H = {"X-Requested-With": "kalmido"}
KEY = base64.b64encode(os.urandom(32)).decode()
OF = "/api/office"
Y = today().year
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001"}


def sql(q, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        return c.execute(q, args).fetchall()
    finally:
        c.close()


def ws(s, v):
    r = s.patch(B + "/api/settings", json={"workspace": v})
    assert r.ok, r.text


def upload(s, data, name="alpha.kalmido-export"):
    r = s.post(B + "/api/account/import", json={"size": len(data), "name": name})
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
        time.sleep(0.25)
    return j


def opened(s, data, rk):
    iid = upload(s, data)
    j = wait(s, iid)
    check(j.get("state") == "key", f"asks for the recovery key {j.get('state')} {j.get('error')}")
    check(s.post(B + f"/api/account/import/{iid}/key", json={"recovery_key": rk}).status_code == 202, "the recovery key is taken")
    j = wait(s, iid)
    check(j.get("state") == "preview", f"opened {j.get('state')} {j.get('error')}")
    return iid


def run(s, iid, target):
    r = s.post(B + f"/api/account/import/{iid}/run", json={"again": True, "target": target, "people": {}})
    check(r.status_code == 202, f"run starts {r.status_code} {r.text[:200]}")
    return wait(s, iid)


def setup_office(s):
    assert s.put(B + OF + "/settings", json={"company_fields": COMPANY, "lang": "de"}).ok
    r = s.post(B + "/api/clients", json={"name": "Testkunde Nord", "street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def invoice(s, cl, rid=None):
    r = s.post(B + OF + "/docs", json={"kind": "invoice", "client_id": cl, "range_id": rid, "service_from": f"{Y}-01-01", "service_to": f"{Y}-01-02",
                                       "items": [{"title": "Tarif Studio", "qty": 1, "rate": 150, "unit": "piece"}]})
    assert r.status_code == 201, r.text
    r = s.post(B + OF + f"/docs/{r.json()['id']}/finalize", json={})
    check(r.ok, f"finalised {r.text[:200]}")
    return r.json() if r.ok else {}


def extra(s, code):
    return next((x for x in s.get(B + OF + "/number-ranges").json().get("extra") or [] if x["code"] == code), {})


if os.environ.get("P6698B_NOSTART") != "1":
    env = dict(os.environ, EXTRA=os.environ.get("EXTRA", "") + f" -e KALMIDO_INSTANCE_MODE=workspaces -e KALMIDO_ORGCRYPT_DELAY=0 -e KALMIDO_SECRET_KEY={KEY}")
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    s0 = requests.Session()
    s0.headers.update(H)
    assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
A.patch(B + f"/api/users/{ALICE}", json={"email": "alice@example.com"})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
GAM = A.post(B + "/api/admin/orgs", json={"name": "Gamma", "admin_id": ALICE}).json()["id"]
DEL = A.post(B + "/api/admin/orgs", json={"name": "Delta", "admin_id": ALICE}).json()["id"]

# ---------------------------------------------------------------- the source: range GT with two invoices, one in the main range
ws(A, f"org:{ORG}")
CL = setup_office(A)
r = A.post(B + "/api/office/num-ranges", json={"code": "GT", "name": "Plattform", "scheme": "GT-{yyyy}-{seq:03}"})
check(r.status_code == 201, "setup: range GT " + r.text[:200])
G = r.json()["id"]
nums = [invoice(A, CL, G).get("number"), invoice(A, CL, G).get("number")]
invoice(A, CL)
check(nums == [f"GT-{Y}-001", f"GT-{Y}-002"], f"setup: two invoices in GT {nums}")

# ---------------------------------------------------------------- export -> import into the empty organisation
r = A.post(B + f"/api/orgs/{ORG}/export")
check(r.status_code == 202, "organisation export started " + r.text[:120])
until(lambda: A.get(B + f"/api/orgs/{ORG}/export").json().get("state") != "running", 120)
OX = su_get(A, B + f"/api/orgs/{ORG}/export/file").content
RK = A.post(B + f"/api/orgs/{ORG}/encryption/recovery", json={"password": "password123"}).json().get("recovery_key", "")
check(OX[:13] == b"KALMIDO-ORGX\n" and RK, "organisation export + recovery key")
iid = opened(A, OX, RK)
j = run(A, iid, GAM)
check(j.get("state") == "done", f"import done {j.get('state')} {j.get('error')} {(j.get('result') or {}).get('warnings')}")
A.delete(B + f"/api/account/import/{iid}")
ws(A, f"org:{GAM}")
x = extra(A, "GT")
check(x.get("id") and x["id"] != G and x.get("scheme") == "GT-{yyyy}-{seq:03}" and x.get("next") == 3 and x.get("used") is True,
      f"the range came along with a new id and its counter {x}")
rows = sql("SELECT number, range_id, chain_key FROM office_docs WHERE org_id=? AND kind='invoice' ORDER BY number", (GAM,))
mine = [r_ for r_ in rows if (r_[0] or "").startswith("GT-")]
check(len(mine) == 2 and all(r_[1] == x.get("id") and r_[2] == f"r{x.get('id')}" for r_ in mine), f"its documents point at the new range, its own chain {rows}")
check(not sql("SELECT 1 FROM office_numbers WHERE org_id=? AND kind=?", (GAM, f"r{G}")), "no counter under the source's id")
CG = setup_office(A)
check(invoice(A, CG, x.get("id")).get("number") == f"GT-{Y}-003", "the next GT invoice in the target is the third")
ch = A.get(B + OF + "/log/chain").json()
check(ch.get("ok") is True and ch.get("pending") == 0, f"the target's chain intact {ch}")

# ---------------------------------------------------------------- Fable F3: the scheme is taken in the target -> imported closed
ws(A, f"org:{DEL}")
CD = setup_office(A)
r = A.post(B + "/api/office/num-ranges", json={"code": "XY", "scheme": "GT-{yyyy}-{seq:03}"})
check(r.status_code == 201, "delta: its own range XY holds the scheme GT-{yyyy}-{seq:03} " + r.text[:160])
iid = opened(A, OX, RK)
j = run(A, iid, DEL)
check(j.get("state") == "done", f"delta: import done {j.get('state')} {j.get('error')}")
A.delete(B + f"/api/account/import/{iid}")
ws(A, f"org:{DEL}")
x3 = extra(A, "GT")
check(x3.get("closed") is True and x3.get("used") is True, f"delta: the imported range GT came closed {x3}")
check("GT" in str((j.get("result") or {}).get("warnings")),
      f"delta: the report names it {(j.get('result') or {}).get('warnings')}")
rows = sql("SELECT number, range_id FROM office_docs WHERE org_id=? AND kind='invoice' AND number LIKE 'GT-%'", (DEL,))
check(len(rows) == 2 and all(r_[1] == x3.get("id") for r_ in rows), f"delta: its documents stay in that range {rows}")
r = A.post(B + OF + "/docs", json={"kind": "invoice", "client_id": CD, "range_id": x3.get("id"), "items": [{"title": "Tarif Studio", "qty": 1, "rate": 150, "unit": "piece"}]})
check(r.status_code in (400, 409), f"delta: no new invoice in the closed range {r.status_code} {r.text[:160]}")
# 2.1399.0 (#7037, Fable F1): opening it again checks its scheme (still XY's) -> refused; with a scheme of its own it opens
r = A.patch(B + f"/api/office/num-ranges/{x3.get('id')}", json={"closed": False})
check(r.status_code == 400 and extra(A, "GT").get("closed") is True, f"#7037 F1: delta: opening with the taken scheme refused {r.status_code} {r.text[:160]}")
r = A.patch(B + f"/api/office/num-ranges/{x3.get('id')}", json={"closed": False, "scheme": "GTD-{yyyy}-{seq:03}"})
check(r.ok and extra(A, "GT").get("closed") is False, f"#7037 F1: delta: with a scheme of its own it opens {r.status_code} {r.text[:160]}")

# ---------------------------------------------------------------- a person without an organisation with a GT of her own imports it
FID, Fr = freelancer(B, A)
ws(Fr, "private")
CF = setup_office(Fr)
r = Fr.post(B + "/api/office/num-ranges", json={"code": "GT", "scheme": "GTP-{yyyy}-{seq:03}"})
check(r.status_code == 201, "freelancer: a range GT of her own " + r.text[:160])
FG = r.json().get("id")
check(invoice(Fr, CF, FG).get("number") == f"GTP-{Y}-001", "freelancer: her own GT invoice")
iid = opened(Fr, OX, RK)
j = run(Fr, iid, "private")
check(j.get("state") == "done", f"freelancer: import done {j.get('error')} {(j.get('result') or {}).get('warnings')}")
x2 = extra(Fr, "GT2")
check(x2.get("scheme") == "GT-{yyyy}-{seq:03}" and x2.get("next") == 3, f"freelancer: the imported range is GT2 with its counter {x2}")
check(extra(Fr, "GT").get("next") == 2 and extra(Fr, "GT").get("id") == FG, "freelancer: her own GT counts on")
check("GT2" in str((j.get("result") or {}).get("warnings")), f"freelancer: the report names the new code {(j.get('result') or {}).get('warnings')}")
check(invoice(Fr, CF, x2.get("id")).get("number") == f"GT-{Y}-003", "freelancer: the imported range continues")

if FAILS:
    print(subprocess.run(["docker", "logs", "--tail", "80", CT], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True).stdout[-8000:], flush=True)
print(f"p6698_b_office_numranges_import: {OKS[0]} ok, {len(FAILS)} failed", flush=True)
sys.exit(1 if FAILS else 0)
