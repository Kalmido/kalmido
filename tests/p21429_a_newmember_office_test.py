#!/usr/bin/env python3
# kalmido-suite: fresh
"""API test (#6527, audit "the first hour of a new customer"): a new member of a company a person created herself starts in the
office with the group "Staff" (only their own receipts, travel, drives and times), not in the silent "Previous access" with
quotations, invoices and the office settings. Invented names and companies only.
 - frida (no organisation) creates "Frida Studio" (POST /api/orgs): orgs.office_new_tpl = staff
 - bob joins as a member: bob has the office group "Staff" (a row, logged as member_start); quotations and
   invoices (GET /api/office/docs, POST a draft) and the office settings (PATCH) are closed to him (403); his own trips open (200)
 - the rights page: frida sees bob in "Staff", "Previous access" is not offered in her company; the log names the start
 - read-only carol starts in "Staff" too (her role changed after joining), a guest sees nothing of the office
 - the role picker of the invitation dialog (GET /api/orgs, roles[].office) says it: member = only their own entries
 - an organisation of the server's admin (POST /api/admin/orgs) keeps "Previous access" for its new members (no row, an update
   changes nothing): the member reads the quotations as before and the role picker says so
 - frida turns bob into an admin and back into a member: he keeps the row he has
 - #7413: the server admin's whole set of admins demotes like admins_remove (the start group + the log); a stored start
   group with special rights (projects) is never given
usage: p21429_a_newmember_office_test.py <datadir>   (KMT_NOSTART=1: against a running instance on KALMIDO_TEST_PORT)"""
import os
import subprocess
import sys
import time

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
from freelancer_fixture import freelancer, org_join  # noqa: E402
from kt import check, done, sess  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
FEAT = "cal,comments,collab,office,clients,docs,files,travel"
OF = "/api/office"


def sql(q, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        return c.execute(q, args).fetchall()
    finally:
        c.close()


if not os.environ.get("KMT_NOSTART"):
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    time.sleep(0.8)
assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True, "modules": ["cal", "comments"]})
ALICE = A.get(B + "/api/state").json()["me"]["id"]

FID, Fr = freelancer(B, A, "frida", FEAT)
r = Fr.post(B + "/api/orgs", json={"name": "Frida Studio"})
check(r.status_code == 201, f"frida creates her company: 201 ({r.status_code} {r.text[:200]})")
OID = r.json()["id"]
check(sql("SELECT office_new_tpl FROM orgs WHERE id=?", (OID,)) == [("staff",)], "her company: new members start in Staff (office_new_tpl)")
Fr.patch(B + "/api/settings", json={"workspace": f"org:{OID}"})


def person(name, role, oid, admin_sess):
    """A new member: added (every way of joining ends in accounts/orgs.py org_member_add, accepting an invitation too), then
    the organisation's admin gives the role."""
    uid, s = freelancer(B, A, name, FEAT)
    r = A.patch(B + f"/api/admin/orgs/{oid}", json={"members_add": [uid]})
    check(r.ok and org_join(B, name, oid), f"{name} joins ({r.status_code} {r.text[:200]})")
    if role != "member":
        r = admin_sess.put(B + f"/api/orgs/{oid}/members", json={"user_id": uid, "role": role})
        check(r.ok, f"{name} gets the role {role} ({r.status_code} {r.text[:200]})")
    s.patch(B + "/api/settings", json={"workspace": f"org:{oid}"})
    return uid, s


def rows(oid, uid):
    return [x[0] for x in sql("SELECT tpl FROM office_rgroup_members WHERE org_id=? AND user_id=? ORDER BY id", (oid, uid))]


# ---------------------------------------------------------------- a member of her company
BOB, Bo = person("bob", "member", OID, Fr)
check(rows(OID, BOB) == ["staff"], f"bob starts in the office group Staff, not in Previous access ({rows(OID, BOB)})")
r = Bo.get(B + OF + "/docs")
check(r.status_code == 403, f"bob does not see quotations and invoices: 403 ({r.status_code} {r.text[:120]})")
r = Bo.post(B + OF + "/docs", json={"kind": "invoice"})
check(r.status_code == 403, f"bob does not write an invoice: 403 ({r.status_code} {r.text[:120]})")
r = Bo.put(B + OF + "/settings", json={"company_fields": {"name": "Not Bob's"}})
check(r.status_code == 403, f"bob does not change the office settings: 403 ({r.status_code} {r.text[:120]})")
r = Bo.get(B + OF + "/trips")
check(r.status_code == 200, f"bob sees his own travel expenses: 200 ({r.status_code} {r.text[:120]})")

# the rights page: bob in Staff, "Previous access" not offered, the start in the log
j = Fr.get(B + OF + "/rights").json()
pb = next((p for p in j.get("people", []) if p["id"] == BOB), {})
check(pb.get("groups") == ["tpl:staff"], f"rights page: bob in Staff ({pb})")
check(j.get("new_tpl") == "staff" and "tpl:legacy" not in [t["ref"] for t in j.get("templates", [])],
      f"rights page: Previous access is not offered in her company ({[t['ref'] for t in j.get('templates', [])]})")
log = Fr.get(B + OF + "/rights/log").json()
items = log.get("items", log) if isinstance(log, dict) else log
check(any(x.get("action") == "member_start" and x.get("user") == BOB and x.get("after") == ["tpl:staff"] for x in items),
      f"rights log: bob's start in Staff ({[x.get('action') for x in items]})")

# read-only carol starts in Staff too, a guest gets no row
CAROL, _ = person("carol", "readonly", OID, Fr)
check(rows(OID, CAROL) == ["staff"], f"read-only carol starts in Staff ({rows(OID, CAROL)})")
GUS, Gu = person("gus", "guest", OID, Fr)
check(Gu.get(B + OF + "/trips").status_code in (403, 404), "a guest sees nothing of the office")

# the invitation dialog's role picker says what the role may in the office
o = next(x for x in Fr.get(B + "/api/orgs").json()["orgs"] if x["id"] == OID)
rm = {x["key"]: x for x in o.get("roles", [])}
check("only their own receipts" in rm.get("member", {}).get("office", ""), f"role picker: a member only their own entries ({rm.get('member')})")
check("everything" in rm.get("admin", {}).get("office", ""), f"role picker: an admin everything ({rm.get('admin')})")

# a role change keeps the row the person has
check(Fr.put(B + f"/api/orgs/{OID}/members", json={"user_id": BOB, "role": "admin"}).ok, "bob becomes an admin")
check(Fr.put(B + f"/api/orgs/{OID}/members", json={"user_id": BOB, "role": "member"}).ok, "bob is a member again")
check(rows(OID, BOB) == ["staff"], f"bob keeps his one Staff row ({rows(OID, BOB)})")

# ---------------------------------------------------------------- an organisation of the server's admin: as before
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha Example", "admin_id": ALICE}).json()["id"]
check(sql("SELECT office_new_tpl FROM orgs WHERE id=?", (ORG,)) == [("",)], "the server admin's organisation: no default group")
A.patch(B + "/api/settings", json={"features": FEAT, "workspace": f"org:{ORG}"})
DAN, Da = person("dan", "member", ORG, A)
check(rows(ORG, DAN) == [], f"dan keeps Previous access there (no row) ({rows(ORG, DAN)})")
r = Da.get(B + OF + "/docs")
check(r.status_code == 200, f"dan reads quotations and invoices as before: 200 ({r.status_code} {r.text[:120]})")
o = next(x for x in A.get(B + "/api/orgs").json()["orgs"] if x["id"] == ORG)
rm = {x["key"]: x for x in o.get("roles", [])}
check("quotations, invoices" in rm.get("member", {}).get("office", ""), f"role picker there: a member works on quotations and invoices ({rm.get('member')})")

# #7413: the server admin's route with the old whole set of admins (no _prev) demotes like admins_remove: with a default
# group the demoted admin starts in it (a row + the log), never in the silent "Previous access"
c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
c.execute("UPDATE orgs SET office_new_tpl='staff' WHERE id=?", (ORG,))
c.commit()
c.close()
ERIC, _ = person("eric", "member", ORG, A)
c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
c.execute("DELETE FROM office_rgroup_members WHERE org_id=? AND user_id=?", (ORG, ERIC))  # an admin of before: no group row
c.commit()
c.close()
check(A.patch(B + f"/api/admin/orgs/{ORG}", json={"admins": [ALICE, ERIC]}).ok and rows(ORG, ERIC) == [], "eric is an admin by the whole set, no group row")
LOG0 = sql("SELECT COUNT(*) FROM office_rights_log WHERE org_id=? AND action='member_start' AND target_user=?", (ORG, ERIC))[0][0]  # his join
r = A.patch(B + f"/api/admin/orgs/{ORG}", json={"admins": [ALICE]})
check(r.ok and sql("SELECT role FROM org_members WHERE org_id=? AND user_id=?", (ORG, ERIC)) == [("member",)], f"the whole set demotes eric ({r.status_code} {r.text[:120]})")
check(rows(ORG, ERIC) == ["staff"], f"#7413: demoted by the whole set, eric starts in Staff ({rows(ORG, ERIC)})")
check(sql("SELECT COUNT(*) FROM office_rights_log WHERE org_id=? AND action='member_start' AND target_user=?", (ORG, ERIC))[0][0] == LOG0 + 1,
      "#7413: the start is in the rights log")
# #7413: only the groups without special rights can be a start group; a stored "projects" counts as none
c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
c.execute("UPDATE orgs SET office_new_tpl='projects' WHERE id=?", (ORG,))
c.commit()
c.close()
FINN, _ = person("finn", "member", ORG, A)
check(rows(ORG, FINN) == [], f"#7413: a start group with special rights is never given ({rows(ORG, FINN)})")

sys.exit(done("p21429_a_newmember_office_test"))
