#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1373.0 (#6357): what a restore of an older backup must not bring back. Invented names only, addresses @example.com.
 guard: every kind with a trash (obj_register / ofk_register / part_kind with trash_prune) has its table in the list of what
   stays deleted (core/objparts.py purged_tables), and every table of the list carries the trigger; absences / sick notes,
   the bookings of outsiders and the video sign-offs are in it
 deleted again: an absence (sick note) and a video sign-off deleted for good after the backup are gone again after it
 scenario A: a deletion asked for after the backup stays (account locked, its day, its plan with the admin's hold); one the
   backup holds but the person cancelled since stays cancelled
 counters: an office number counter that moved on after the backup is not set back (no invoice number twice); a counter of an
   organisation the backup does not have is left alone
usage: p21373_b_restore_test.py <datadir>
freelancer-matrix: admin (the restore is the instance's; the accounts are persons without an organisation)"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
import kt  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, CT, FAILS, OKS, check, sess  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
PW = kt.PASSWORD
kt.fresh(env={"KALMIDO_INSTANCE_MODE": "workspaces"}, prefix="P21373B")
A = kt.setup()
NOW = datetime.now(timezone.utc)


def ago(days):
    return (NOW - timedelta(days=days)).isoformat(timespec="seconds")


def sql(q, args=(), write=False):
    c = dbxm.connect(DATA)
    try:
        r = c.execute(q, args)
        rows = None if write else r.fetchall()
        c.commit()
        return rows
    finally:
        c.close()


def py(code):
    """Lines inside the container -> its output."""
    r = subprocess.run(["docker", "exec", "-i", CT, "python", "-c", "import app, json\nfrom kalmido.core.db import connect\nfrom kalmido.core.pg import system_ctx\n"
                        "c = connect()\nwith system_ctx(c):\n" + "\n".join("    " + x for x in code.strip().split("\n")) + "\n    c.commit()\nc.close()"],
                       capture_output=True, text=True, timeout=300)
    return r.stdout + r.stderr


def last_json(out):
    return json.loads([x for x in out.splitlines() if x.startswith("{")][-1])


def restore(name):
    r = A.post(B + "/api/admin/backups/restore", json={"name": name, "confirm": "RESTORE", "password": PW})
    check(r.ok, f"restore {r.status_code} {r.text[:200]}")
    return r.json() if r.ok else {}


# ------ the guard: every kind with a trash is in the list, every table of the list has the trigger
g = last_json(py("""from kalmido.core.objhooks import OBJ
from kalmido.core.objparts import PART_KINDS, purged_tables
kinds = {k: r['table'] for k, r in OBJ.items() if r.get('trash_prune')}
kinds.update({k: p['table'] for k, p in PART_KINDS.items() if p['trash_prune'] and k not in OBJ})
print(json.dumps({'kinds': kinds, 'list': list(purged_tables())}))"""))
LIST = g["list"]
check(len(g["kinds"]) >= 20, f"guard: the register names the kinds with a trash ({len(g['kinds'])})")
missing = sorted(f"{k} ({t})" for k, t in g["kinds"].items() if t not in LIST)
check(not missing, f"guard: every kind with trash_prune is in the list of what stays deleted (missing: {missing})")
for t in ("hub_absences", "appt_bookings", "video_reviews", "office_signoffs", "bookmarks", "tchat_msgs", "obj_comments"):
    if t == "obj_comments" and t not in g["kinds"].values():
        continue  # (only while the comments' core runs the trash period itself)
    check(t in LIST, f"guard: {t} is in the list")
check(LIST[:3] == ["orgs", "lists", "tasks"], f"guard: the big ones first {LIST[:3]}")
have = {r[0] for r in sql("SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid WHERE t.tgname LIKE 'kalmido_purged_%'")}
check(not [t for t in LIST if t not in have], f"guard: every table of the list carries the trigger (without: {[t for t in LIST if t not in have]})")

# ------ the data before the backup
FR, Fr = freelancer(B, A, "frieda")  # a person without an organisation
HE, He = freelancer(B, A, "hedda")  # asks for the deletion of her account after the backup
CA, Ca = freelancer(B, A, "carla")  # asked before the backup, cancelled since
ABS = sql("INSERT INTO hub_absences(org_id, user_id, kind, start_date, end_date, created_at) VALUES(NULL,?,'sick','2026-03-02','2026-03-04',?) RETURNING id",
          (FR, ago(100)))[0][0]
VR = sql("INSERT INTO video_reviews(owner_id, title, created_by, created_at, updated_at) VALUES(?,?,?,?,?) RETURNING id",
         (FR, "Cut 3 sign-off", FR, ago(100), ago(100)))[0][0]
ORG = sql("INSERT INTO orgs(name, created_at) VALUES('Example office', ?) RETURNING id", (ago(200),))[0][0]
sql("INSERT INTO office_numbers(org_id, kind, period, last) VALUES(?,?,?,?)", (ORG, "invoice", "2026", 5), write=True)
CA_AT = (NOW + timedelta(days=20)).isoformat(timespec="seconds")
sql("UPDATE users SET disabled=true, delete_at=?, delete_plan=? WHERE id=?", (CA_AT, json.dumps({"how": "self", "agents": []}), CA), write=True)
BK = last_json(py("from kalmido.admin import backup as bk\nprint(json.dumps({'name': bk.bk_create('manual')}))"))["name"]

# ------ after the backup: deleted for good, a deletion asked for, one cancelled, the counter moves on
sql("DELETE FROM hub_absences WHERE id=?", (ABS,), write=True)
py(f"from kalmido.core.objhooks import OBJ\nfrom kalmido.core.writes import _purge_rows\nk = [k for k, r in OBJ.items() if r['table'] == 'video_reviews'][0]\n_purge_rows(c, k, OBJ[k], {VR})")
check(not sql("SELECT 1 FROM video_reviews WHERE id=?", (VR,)), "the video sign-off is deleted for good")
for t, i in (("hub_absences", ABS), ("video_reviews", VR)):
    check(bool(sql("SELECT 1 FROM purged_rows WHERE tbl=? AND ref_id=?", (t, i))), f"{t}: the delete for good is noted")
    sql("UPDATE purged_rows SET at=? WHERE tbl=? AND ref_id=?", (ago(40), t, i), write=True)  # older than the last days
HE_AT = (NOW + timedelta(days=30)).isoformat(timespec="seconds")
HE_PLAN = json.dumps({"how": "self", "agents": [], "admin": "alice", "asked": ago(0)})  # #6395: an admin's hold rides along
sql("UPDATE users SET disabled=true, delete_at=?, delete_plan=? WHERE id=?", (HE_AT, HE_PLAN, HE), write=True)
sql("UPDATE users SET disabled=false, delete_at=NULL, delete_plan='' WHERE id=?", (CA,), write=True)
sql("UPDATE office_numbers SET last=9 WHERE org_id=?", (ORG,), write=True)
ORG2 = sql("INSERT INTO orgs(name, created_at) VALUES('Later office', ?) RETURNING id", (ago(1),))[0][0]
sql("INSERT INTO office_numbers(org_id, kind, period, last) VALUES(?,?,?,?)", (ORG2, "invoice", "2026", 3), write=True)
he_before = sql("SELECT delete_at, delete_plan FROM users WHERE id=?", (HE,))[0]

# ------ the restore of the older backup
j = restore(BK)
A = sess("alice")
check(not sql("SELECT 1 FROM hub_absences WHERE id=?", (ABS,)), "deleted again: the sick note is gone again")
check(not sql("SELECT 1 FROM video_reviews WHERE id=?", (VR,)), "deleted again: the video sign-off is gone again (the core's way)")
check((j.get("deleted_again") or {}).get("entries", 0) >= 2, f"deleted again: counted {j.get('deleted_again')}")

he = sql("SELECT disabled, delete_at, delete_plan FROM users WHERE id=?", (HE,))[0]
check(he[0] is True, "scenario A: the account stays locked")
check((he[1], he[2]) == tuple(he_before), f"scenario A: its day and plan stay as before the restore {he[1:]} / {he_before}")
check(json.loads(he[2]).get("admin") == "alice", "scenario A: the admin's hold rides along (#6395)")
ca = sql("SELECT disabled, delete_at, delete_plan FROM users WHERE id=?", (CA,))[0]
check(ca[0] is False and ca[1] is None and ca[2] == "", f"a deletion cancelled since stays cancelled {ca}")
check(j.get("deletions_kept") == {"again": 1, "cancelled": 1}, f"the result names both {j.get('deletions_kept')}")

check(sql("SELECT last FROM office_numbers WHERE org_id=? AND kind='invoice'", (ORG,)) == [(9,)], "counters: the invoice counter is not set back")
check(not sql("SELECT 1 FROM orgs WHERE id=?", (ORG2,)), "counters: the organisation made after the backup is not there")
check(not sql("SELECT 1 FROM office_numbers WHERE org_id=?", (ORG2,)), "counters: its counter is left alone")
check(j.get("counters_raised") == 1, f"counters: the result names it {j.get('counters_raised')}")

# ------ the same backup again: nothing left to change
j = restore(BK)
A = sess("alice")
check(j.get("deletions_kept") == {"again": 1, "cancelled": 1}, f"again: the same state as before the restore {j.get('deletions_kept')}")
check(sql("SELECT last FROM office_numbers WHERE org_id=? AND kind='invoice'", (ORG,)) == [(9,)], "again: the counter stays")

print(f"p21373_b_restore: {OKS[0]} ok, {len(FAILS)} failed", flush=True)
sys.exit(1 if FAILS else 0)
