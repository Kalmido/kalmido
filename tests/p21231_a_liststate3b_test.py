#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1231.0 (#5880, stage 3b of the projects' state marker, one-way): the old column archived of lists goes. Before the
fragment migrations.d/5880_a.py drops it, core/liststate.py lst_move (every start while it is there) fills archived_at where
it was archived without a moment (before 1.6.1), clears a stale one, sets the marker from it once more and raises the back
limit; the trigger kalmido_list_state reads archived_at since. Invented names.
 - a database of before (the suite adds the column back with the values of an older version and restarts): the column is gone
   after the start, every project keeps its archive (archived without a moment, a stale moment, archived in the trash, a row
   of a dump from before the marker), the back limit names #5880
 - a second start finds nothing to do (the column is gone); a row marked archived without archived_at keeps its archive
 - "my data" (GET /api/export.json) still gives the key archived, from the marker
 - the account import: a file's archived (a file of before) or state (a file without the key) decides the archive
 - the undo of the settings: a copy of before the column went is written back as archive / archived_at, and a step of
   before still matches its fingerprint (core/writes.py undo_gone)
 - archiving / restoring through the route as a person without an organisation still works (the whole table agrees)
freelancer-matrix: tasks (a person without an organisation keeps her archived projects through the move)
usage: p21231_a_liststate3b_test.py <datadir>"""
from kt import su_get  # 2.1444 (#6586): export.json behind the step-up (POST + ticket); before the code below (E402)
import json
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import B, check, dbx, done, fresh, sess  # noqa: E402
from obj_probe import in_app  # noqa: E402
import dbx as dbxm  # noqa: E402
import kt  # noqa: E402

fresh(prefix="P21231A")

assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Example Studio", "lang": "en", "collab_all": True})
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEATURES})
FID, Fr = freelancer(B, A)
COL = "SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='lists' AND column_name='archived'"


def plist(name):
    r = Fr.post(B + "/api/lists", json={"name": name, "org_id": None})
    check(r.ok, f"setup: project {name} {r.text[:120]}")
    return r.json().get("id")


def row(lid):
    r = dbx("SELECT state, archived_at IS NOT NULL, deleted_at IS NOT NULL FROM lists WHERE id=?", (lid,))
    return tuple(r[0]) if r else None


def owner(sql):
    """The suite's own session (the app's account does not own the table)."""
    dbxm.connect(os.path.join(kt.DATA, "tasks.db")).executescript(sql + "\n")


check(not dbx(COL), "a new database has no column archived on lists")

# ---------------------------------------------------------------- a database of before
P1 = plist("Example Pottery Course")   # archived before 1.6.1: archived, no archived_at
P2 = plist("Example Bike Repair")      # out of the archive before 2.1054.0: not archived, archived_at left
P3 = plist("Example Old Workshop")     # archived, then into the trash
P4 = plist("Example Garden Plan")      # a dump of before the marker: archived, state 'live'
P5 = plist("Example Kitchen Shelves")  # live, stays live
for p in (P1, P3, P4):
    check(Fr.patch(B + f"/api/lists/{p}", json={"archived": True}).ok, f"setup: archived {p}")
check(Fr.delete(B + f"/api/lists/{P3}").ok and row(P3)[0] == "trash", f"setup: P3 in the trash {row(P3)}")
owner(f"""ALTER TABLE lists ADD COLUMN archived BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE lists DISABLE TRIGGER kalmido_list_state;
UPDATE lists SET archived=true WHERE id IN ({int(P1)}, {int(P3)}, {int(P4)});
UPDATE lists SET archived_at=NULL WHERE id={int(P1)};
UPDATE lists SET archived_at='2026-01-02T03:04:05+00:00' WHERE id={int(P2)};
UPDATE lists SET state='live', archived_at=NULL WHERE id={int(P4)};
ALTER TABLE lists ENABLE TRIGGER kalmido_list_state;""")
check(dbx(COL) and row(P1) == ("archived", False, False) and row(P2) == ("live", True, False) and row(P4) == ("live", False, False),
      f"setup: the column back with the values of an older version {row(P1)} {row(P2)} {row(P4)}")
fresh(keep=True, prefix="P21231A")

check(not dbx(COL), "after the start: the column archived is gone")
check(row(P1) == ("archived", True, False), f"archived before 1.6.1: still archived, archived_at filled {row(P1)}")
check(row(P2) == ("live", False, False), f"a stale archived_at of a project out of the archive: cleared, live {row(P2)}")
check(row(P3) == ("trash", True, True), f"archived and in the trash: in the trash, its archive kept {row(P3)}")
check(row(P4) == ("archived", True, False), f"a row of a dump from before the marker: archived from the column {row(P4)}")
check(row(P5) == ("live", False, False), f"a live project stays live {row(P5)}")
meta = dict(dbx("SELECT key, value FROM kalmido_meta WHERE key IN ('back_floor', 'back_floor_how')"))
check("#5880" in (meta.get("back_floor_how") or "") and meta.get("back_floor", "").endswith(".0"),
      f"the back limit is raised and names the move {meta}")
# review 2.1231: a row marked archived without its moment (the trigger off, hand-made SQL) keeps its archive at the next start
owner(f"""ALTER TABLE lists DISABLE TRIGGER kalmido_list_state;
UPDATE lists SET state='archived', archived_at=NULL WHERE id={int(P5)};
ALTER TABLE lists ENABLE TRIGGER kalmido_list_state;""")
check(row(P5) == ("archived", False, False), f"setup: marked archived without archived_at {row(P5)}")
fresh(keep=True, prefix="P21231A")
check(not dbx(COL) and row(P1) == ("archived", True, False) and row(P2) == ("live", False, False),
      f"a second start: nothing to do {row(P1)} {row(P2)}")
check(row(P5) == ("archived", True, False), f"the start's reconcile: archived without a moment gets one, stays archived {row(P5)}")
dbx("UPDATE lists SET state='live' WHERE id=?", (P5,))
check(row(P5) == ("live", False, False), f"setup: P5 live again {row(P5)}")
check("None" in in_app("from kalmido.core.liststate import lst_move\nprint(lst_move(c))"), "lst_move without the column: nothing (None)")

# ---------------------------------------------------------------- the app as before, through the route
Fr = sess("frida")
ls = {x["id"]: x for x in Fr.get(B + "/api/state").json().get("lists", [])}
check(ls.get(P1, {}).get("archived") in (1, True) and ls.get(P1, {}).get("name") == "Example Pottery Course",
      f"the project list shows the archived project with its name {ls.get(P1)}")
check(ls.get(P2, {}).get("archived") in (0, False) and ls.get(P2, {}).get("name") == "Example Bike Repair",
      f"the project list shows the live one {ls.get(P2)}")
r = Fr.patch(B + f"/api/lists/{P1}", json={"archived": False})
check(r.ok and row(P1) == ("live", False, False), f"out of the archive through the route {r.status_code} {row(P1)}")
r = Fr.patch(B + f"/api/lists/{P5}", json={"archived": True})
check(r.ok and row(P5) == ("archived", True, False), f"into the archive through the route {r.status_code} {row(P5)}")

# ---------------------------------------------------------------- "my data" keeps the key archived
ex = su_get(Fr, B + "/api/export.json")
el = {x["id"]: x for x in (ex.json().get("lists", []) if ex.ok else [])}
check(el.get(P5, {}).get("archived") == 1 and el.get(P1, {}).get("archived") == 0 and el.get(P5, {}).get("name") == "Example Kitchen Shelves",
      f"my data: archived from the marker, with the name {ex.status_code} {[(k, v.get('archived')) for k, v in el.items()][:6]}")

# ---------------------------------------------------------------- the account import: the file's archive
out = in_app(f"""import json
from kalmido.admin.acctimport import umz_row
ts = '2026-11-15T10:00:00+00:00'
res = {{}}
for k, src in (("old_on", {{"name": "Example A", "archived": 1, "archived_at": None}}),
               ("old_off", {{"name": "Example B", "archived": 0, "archived_at": "2026-01-02T03:04:05+00:00"}}),
               ("state_only", {{"name": "Example C", "state": "archived"}}),
               ("new_on", {{"name": "Example D", "state": "archived", "archived": 1, "archived_at": "2026-01-02T03:04:05+00:00"}})):
    d = umz_row(c, "lists", src, {{"owner_id": {int(FID)}}}, ts) or {{}}
    res[k] = [d.get("state"), bool(d.get("archived_at")), "archived" in d]
print("IMP", json.dumps(res))""")
imp = json.loads(next((x[4:] for x in out.splitlines() if x.startswith("IMP ")), "{}"))
check(imp.get("old_on") == ["archived", False, False] and imp.get("old_off") == ["live", False, False],
      f"a file of before: its archived decides, a stale moment is dropped, the key is no column {imp} {out[-300:]}")
check(imp.get("state_only") == ["archived", False, False] and imp.get("new_on") == ["archived", True, False],
      f"a file without the key: state decides; a file of now keeps its moment {imp}")

# ---------------------------------------------------------------- the undo of a copy of before
out = in_app("""import json
from kalmido.core import writes
import kalmido.lists.lmcore  # noqa: F401  (registers undo_gone for lists)
back = writes.UNDO_GONE["lists"][1]
a = back({"name": "x", "archived": 1, "archived_at": None})
b = back({"name": "x", "archived": 0, "archived_at": "2026-01-02T03:04:05+00:00"})
d = back({"name": "x", "archived_at": "2026-01-02T03:04:05+00:00"})
old = {"lists": [{"id": 7, "name": "x", "archived": 1, "archived_at": "2026-01-02T03:04:05+00:00"}]}
now = {"lists": [{"id": 7, "name": "x", "archived_at": "2026-01-02T03:04:05+00:00"}]}
other = {"lists": [{"id": 7, "name": "y", "archived_at": "2026-01-02T03:04:05+00:00"}]}
print("UND", json.dumps({"a": [bool(a.get("archived_at")), "archived" in a], "b": [b.get("archived_at"), "archived" in b],
                         "d": d.get("archived_at"), "fp": writes._fp_is(now, {}, writes._fp(old)),
                         "fp_other": writes._fp_is(other, {}, writes._fp(old))}))""")
und = json.loads(next((x[4:] for x in out.splitlines() if x.startswith("UND ")), "{}"))
check(und.get("a") == [True, False] and und.get("b") == [None, False] and und.get("d") == "2026-01-02T03:04:05+00:00",
      f"a copy of before written back: its archive as archived_at, the old key gone; a copy of now unchanged {und} {out[-300:]}")
check(und.get("fp") is True and und.get("fp_other") is False,
      f"a step of before matches its fingerprint while nothing else changed, not after another change {und}")

# ---------------------------------------------------------------- the whole table
bad = dbx("""SELECT id, state, archived_at FROM lists WHERE state IS DISTINCT FROM
             (CASE WHEN deleted_at IS NOT NULL THEN 'trash' WHEN archived_at IS NOT NULL THEN 'archived' ELSE 'live' END)""")
check(not bad, f"every project's marker agrees with archived_at / deleted_at {bad[:3]}")

sys.exit(done("p21231_a_liststate3b"))
