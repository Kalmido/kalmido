#!/usr/bin/env python3
# kalmido-suite:
"""2.1364.0 part C (#6297, audit #4741): the security hardening round, points 1-7, one section each. One container
(start.sh, mode workspaces); invented names only (example.com).
 1 an organisation invitation ends with its admin's right (demoted: the rows go; a right lost on a way without the hook:
   accepting is refused, OJN_BY); audit #4818 (b) an instance admin adding the invited person directly and removing her
   again leaves no invitation to come back by; (c) a demotion of an admin waits for the organisation's row (FOR UPDATE)
 2 a text that only starts like a sealed value ("kenc1:...") is sealed like any other (the ledger entry of a person without
   an organisation reads, changes and deletes again; freelancer-matrix: office); a real sealed value is kept
usage: p21364_c_haertung_test.py <datadir>"""
import base64
import os
import subprocess
import sys
import threading

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
import testclock  # noqa: E402
import dbx as dbxm  # noqa: E402
from freelancer_fixture import freelancer, org_join  # noqa: E402
from kt import B, CT, DATA, check, dbx, sess, until  # noqa: E402

kt.fresh(env={"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ORGCRYPT_DELAY": "0",
              "KALMIDO_SECRET_KEY": base64.b64encode(os.urandom(32)).decode()}, prefix="P21364C")
A = kt.setup()
ids = {}
for u in ("bob", "carl", "dora", "erna", "gerda"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": kt.PASSWORD, "email": f"{u}@example.com"})
    assert r.ok, r.text
    ids[u] = r.json()["id"]
BOB, CARL, DORA, ERNA, GERDA = (ids[u] for u in ("bob", "carl", "dora", "erna", "gerda"))
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": BOB})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
dbx("DELETE FROM org_members WHERE org_id=? AND user_id<>?", (ORG, BOB))
kt.proved()  # an organisation admin invites by address only an account that proved it
Bo = sess("bob")


def joins(user):
    return [j["org_id"] for j in sess(user).get(B + "/api/orgs").json().get("joins", [])]


def invite(s, email, role="member"):
    return s.put(B + f"/api/orgs/{ORG}/members", json={"email": email, "role": role}).ok


# ==== 1: an invitation ends with its admin's right
check(invite(Bo, "carl@example.com", "admin") and org_join(B, "carl", ORG), "(1) setup: carl joins Alpha as admin")
Ca = sess("carl")
check(invite(Ca, "dora@example.com") and ORG in joins("dora"), "(1) carl (admin) invites dora: her invitation is open")
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": CARL, "role": "member"}).ok, "(1) bob demotes carl to member")
check(ORG not in joins("dora") and sess("dora").post(B + f"/api/orgs/{ORG}/join").status_code == 404,
      "(1) carl's invitation of dora ended with his admin right (not listed, accepting 404)")
check(dbx("SELECT COUNT(*) FROM org_joins WHERE org_id=? AND created_by=?", (ORG, CARL))[0][0] == 0, "(1) carl's invitation rows went")
# a right that ends on a way without the hook (a row changed by hand): accepting checks the inviter itself (OJN_BY)
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": CARL, "role": "admin"}).ok and invite(Ca, "erna@example.com"),
      "(1) carl is admin again and invites erna")
dbx("UPDATE org_members SET role='member' WHERE org_id=? AND user_id=?", (ORG, CARL))
check(ORG not in joins("erna") and sess("erna").post(B + f"/api/orgs/{ORG}/join").status_code == 404,
      "(1) carl no admin (row changed directly): erna's invitation is not open, accepting 404")
dbx("UPDATE org_members SET role='admin' WHERE org_id=? AND user_id=?", (ORG, CARL))
check(org_join(B, "erna", ORG), "(1) carl admin again: erna accepts (only the inviter's right closed it)")
check([r[0] for r in dbx("SELECT role FROM org_members WHERE org_id=? AND user_id=?", (ORG, ERNA))] == ["member"], "(1) erna is a member")

# (b) audit #4818: the instance admin adds the invited person directly and removes her: no invitation is left to return by
check(invite(Bo, "gerda@example.com", "admin") and ORG in joins("gerda"), "(1b) bob invites gerda as admin")
check(A.patch(B + f"/api/admin/orgs/{ORG}", json={"members_add": [GERDA]}).ok, "(1b) the instance admin adds gerda directly")
check(dbx("SELECT COUNT(*) FROM org_joins WHERE org_id=? AND user_id=?", (ORG, GERDA))[0][0] == 0, "(1b) her invitation row went with the adding")
check(A.patch(B + f"/api/admin/orgs/{ORG}", json={"members_remove": [GERDA]}).ok, "(1b) the instance admin removes gerda")
check(sess("gerda").post(B + f"/api/orgs/{ORG}/join").status_code == 404 and not dbx(
      "SELECT 1 FROM org_members WHERE org_id=? AND user_id=?", (ORG, GERDA)), "(1b) gerda cannot come back as admin by the old invitation")
# org_leave: a row left beside a membership (an older server) goes when the person leaves
dbx("INSERT INTO org_joins(org_id,user_id,role,created_by,created_at) VALUES(?,?,'admin',?,now())", (ORG, ERNA, BOB))
check(sess("erna").delete(B + f"/api/orgs/{ORG}/members/{ERNA}").ok, "(1b) erna leaves Alpha")
check(dbx("SELECT COUNT(*) FROM org_joins WHERE org_id=? AND user_id=?", (ORG, ERNA))[0][0] == 0
      and sess("erna").post(B + f"/api/orgs/{ORG}/join").status_code == 404, "(1b) leaving took her invitation row along (no way back)")

# (c) audit #4818: a demotion of an admin locks the organisation's row before counting the admins
dbc, dbn = dbxm._target(DATA)
hold = subprocess.Popen(["docker", "exec", "-i", dbc, "psql", "-U", "kalmido", "-d", dbn, "-X", "-q", "-A", "-t"], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
hold.stdin.write(f"BEGIN;\nSELECT id FROM orgs WHERE id={int(ORG)} FOR UPDATE;\n\\echo held\n")
hold.stdin.flush()
check(until(lambda: hold.stdout.readline().strip() == "held", 30), "(1c) a second session holds Alpha's row")
res = {}
t = threading.Thread(target=lambda: res.update(r=sess("carl").put(B + f"/api/orgs/{ORG}/members", json={"user_id": CARL, "role": "member"})))
t.start()


def waiting():
    return dbx("SELECT 1 FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%FROM orgs WHERE id=% FOR UPDATE%' "
               "AND query NOT LIKE '%pg_stat_activity%'") or ("r" in res)


check(until(waiting, 30) and "r" not in res, "(1c) carl stepping down waits for the organisation's row (no count without it)")
hold.stdin.write("COMMIT;\n")
hold.stdin.close()
hold.wait(30)
t.join(60)
check("r" in res and res["r"].ok, f"(1c) after the other session ends, the demotion goes through ({res.get('r') and res['r'].status_code})")
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": BOB, "role": "member"}).status_code == 409,
      "(1c) bob, now the only admin, cannot step down (counted after the lock)")


def py_in_app(code):
    """Python inside the app container, one transaction (system context)."""
    r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0", CT, "python", "-c",
                        "import app\nfrom kalmido.core.db import connect\nfrom kalmido.core.pg import system_ctx\nc = connect()\n"
                        "with system_ctx(c):\n" + "".join("    " + x + "\n" for x in code.splitlines()) + "c.commit()\nc.close()"],
                       capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


# ==== 2: a text that only looks sealed
FAKE = "kenc1:AAAA"
FID, Fr = freelancer(B, A, "frida")
Fr.patch(B + "/api/settings", json={"features": "cal,comments,collab,office,clients,docs"})
check(Fr.put(B + "/api/office/settings", json={"lang": "de", "currency": "EUR", "company_fields": {"name": "Frida Beispiel"}}).ok, "(2) setup: frida's office")
check(Fr.put(B + "/api/office/books/ledger/settings", json={"method": "balance", "size": "small"}).ok, "(2) setup: balance sheet")
DAY = testclock.today().isoformat()
r = Fr.post(B + "/api/office/books/ledger/entries", json={"day": DAY, "debit": "6825", "credit": "3070", "amount": "5.00", "text": FAKE})
check(r.status_code == 201, f"(2) an entry with the text {FAKE} {r.status_code} {r.text[:120]}")
E = r.json() if r.ok else {}
raw = dbx("SELECT text FROM office_ledger_entries WHERE id=?", (E.get("id", 0),))
check(raw and raw[0][0] != FAKE, f"(2) not stored as it came (sealed like any text): {raw and raw[0][0][:20]}")
r = Fr.get(B + f"/api/office/books/ledger?year={DAY[:4]}")
mine = [e for e in (r.json().get("entries") or []) if e.get("id") == E.get("id")] if r.ok else []
check(r.ok and mine and mine[0].get("text", "").lstrip("\u200b") == FAKE, f"(2) the year reads (was 500) and shows the text {r.status_code}")
r = Fr.put(B + f"/api/office/books/ledger/entries/{E.get('id')}", json={"text": FAKE + "B", "expect_updated_at": E.get("updated_at")})
check(r.ok, f"(2) the entry can be changed {r.status_code}")
check(Fr.delete(B + f"/api/office/books/ledger/entries/{E.get('id')}").ok, "(2) and deleted")
out = py_in_app(f"from kalmido.core import orgcrypt as oc\nv = oc.oc_enc(c, {ORG}, 't.c', 'geheim')\n"
                f"print('KEEP', oc.oc_enc(c, {ORG}, 't.c', v) == v, oc.oc_dec(c, {ORG}, 't.c', oc.oc_enc(c, {ORG}, 't.c', '{FAKE}')).lstrip(chr(8203)) == '{FAKE}',"
                f" oc.oc_enc(c, {ORG}, 't.d', v) != v)")
check("KEEP True True True" in out, f"(2) a real sealed value is kept, a fake one sealed, one of another place sealed anew: {out[-300:]}")

sys.exit(kt.done("p21364_c_haertung"))
