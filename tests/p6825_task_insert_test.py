#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1358.0 (#6825): task_insert() of kalmido/tasks/repo.py, the one way a new task is written. Own container. Invented names only.
 - the helper in the app container: created_by = the given account (None = no creator), created_at = updated_at = ts (default
   now), each of them settable on its own; sort TOP = above the list's top-level tasks, END = below them, a number as given
   (a subtask's TOP among its siblings); further columns as given; the ticket number comes from the trigger (a project with a key
   numbers on), ticket_no / a column that is no name / no title are refused
 - the ways that went onto it keep their columns: POST /api/tasks (on top, created_by + origin person), a repeating task
   ticked (the done copy keeps created_by, created_at and its project number is the next), a task template applied (its
   subtask below it), a person without an organisation creates a task in her inbox
freelancer-matrix: task create (a person without an organisation creates a task in her inbox, on top)
usage: p6825_task_insert_test.py <datadir>"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kt  # noqa: E402
from kt import B, CT, check, dbx  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

kt.fresh()
A = kt.setup()
AID = kt.me_id(A)


def box(code):
    """Python inside the app container (as the system) -> the last line it prints, parsed as JSON."""
    out = subprocess.run(["docker", "exec", CT, "python", "-c", "import app, json\nfrom kalmido.core.db import connect\n"
                          "from kalmido.core.pg import system_ctx\nfrom kalmido.tasks.repo import END, TOP, task_insert\n"
                          "c = connect()\nwith system_ctx(c):\n"
                          + "".join("    " + ln + "\n" for ln in code.splitlines()) + "c.commit()\nc.close()"],
                         capture_output=True, text=True, timeout=300)
    check(out.returncode == 0, f"the run in the container works {out.stderr[-800:]}")
    lines = out.stdout.strip().splitlines()
    return json.loads(lines[-1]) if lines else None


def row(tid):
    r = dbx("SELECT * FROM tasks WHERE id=?", (tid,))
    return dict(r[0]) if r else {}


r = A.post(B + "/api/lists", json={"name": "Garden project"})
check(r.ok, f"a project {r.text[:200]}")
LID = r.json()["id"]
first = A.post(B + "/api/tasks", json={"title": "Dig the bed", "list_id": LID}).json()["id"]
f0 = row(first)

# ---- the helper itself
out = box(f"""
a = task_insert(c, {AID}, {LID}, title="Top one")
b = task_insert(c, {AID}, {LID}, title="End one", sort=END)
n = task_insert(c, None, {LID}, title="Placed", sort=17.5, ts="2026-01-02T03:04:05Z", content="note", priority=2)
s = task_insert(c, {AID}, {LID}, title="Sub", parent_id=a, sort=TOP)
d = task_insert(c, {AID}, {LID}, title="Dated", created_at="2025-05-05T05:05:05Z")
errs = []
for kw in ({{"title": "x", "ticket_no": 9}}, {{"title": "x", "content=1;--": "y"}}, {{}}):
    try:
        task_insert(c, {AID}, {LID}, **kw)
        errs.append("none")
    except (ValueError, TypeError) as e:
        errs.append(type(e).__name__)
print(json.dumps({{"a": a, "b": b, "n": n, "s": s, "d": d, "errs": errs}}))
""")
ta, tb, tn, ts_, td = (row(out[k]) for k in "abnsd")
check(ta["created_by"] == AID and ta["title"] == "Top one" and ta["list_id"] == LID and ta["parent_id"] is None,
      f"the required columns {ta}")
check(ta["sort"] == f0["sort"] - 1, f"TOP = above the top-level tasks ({ta['sort']} vs {f0['sort']})")
check(tb["sort"] == max(f0["sort"], ta["sort"]) + 1, f"END = below them {tb['sort']}")
check(tn["created_by"] is None and tn["sort"] == 17.5 and tn["content"] == "note" and tn["priority"] == 2,
      f"no creator, a sort as given, further columns as given {tn}")
check(str(tn["created_at"]).startswith("2026-01-02") and str(tn["updated_at"]).startswith("2026-01-02"), f"ts = created_at and updated_at {tn}")
check(ts_["parent_id"] == out["a"] and ts_["sort"] == -1, f"a subtask: TOP among its siblings (none yet: -1) {ts_}")
check(str(td["created_at"]).startswith("2025-05-05") and not str(td["updated_at"]).startswith("2025-05-05"),
      f"created_at on its own, updated_at stays now {td}")
check(out["errs"] == ["ValueError", "ValueError", "TypeError"], f"ticket_no / a bad column name / no title are refused {out['errs']}")
check(not dbx("SELECT 1 FROM tasks WHERE title='x'"), "a refused insert writes nothing")

# ---- the ticket number of a project with a key comes from the trigger, also through task_insert
dbx("UPDATE lists SET tickets=1, ticket_key='GRD' WHERE id=?", (LID,))
k1 = A.post(B + "/api/tasks", json={"title": "Plant roses", "list_id": LID}).json()["id"]
out = box(f"""print(json.dumps(task_insert(c, None, {LID}, title="From a mail")))""")
n1, n2 = row(k1)["ticket_no"], row(out)["ticket_no"]
check(n1 and n2 == n1 + 1, f"the helper's task gets the next number of the project ({n1}, {n2})")

# ---- the route POST /api/tasks: on top, creator + origin
top = A.post(B + "/api/tasks", json={"title": "Water the lawn", "list_id": LID}).json()["id"]
tt = row(top)
mins = dbx("SELECT MIN(sort) FROM tasks WHERE list_id=? AND parent_id IS NULL AND id<>?", (LID, top))[0][0]
check(tt["created_by"] == AID and tt["origin"] == "person" and tt["sort"] == mins - 1 and tt["ticket_no"] == n2 + 1,
      f"POST /api/tasks: creator, origin, on top, the next number {tt}")
r = A.get(B + f"/api/tasks/{top}")
check(r.ok and r.json()["title"] == "Water the lawn", f"the new task opens {r.status_code}")

# ---- a repeating task ticked: the done copy keeps its columns, the project numbers on
rep = A.post(B + "/api/tasks", json={"title": "Mow", "list_id": LID, "due": "2030-01-01", "repeat": "FREQ=DAILY"}).json()["id"]
r0 = row(rep)
r = A.post(B + "/api/tasks/batch", json={"ids": [rep], "action": "complete", "data": {}})
check(r.ok, f"the tick {r.text[:200]}")
cp = dbx("SELECT * FROM tasks WHERE list_id=? AND title='Mow' AND status=2", (LID,))
cp = dict(cp[0]) if cp else {}
check(cp and cp["created_by"] == AID and cp["created_at"] == r0["created_at"] and cp["sort"] == r0["sort"] and cp["repeat"] == ""
      and cp["ticket_no"] == r0["ticket_no"] + 1 and row(rep)["due"] == "2030-01-02",
      f"the done copy keeps creator / created_at / sort, gets the next number; the original moves on {cp}")

# ---- a task template applied: task + subtask, in the target list, mine (lists/templates.py tpl_insert)
par = A.post(B + "/api/tasks", json={"title": "Cut the hedge", "list_id": LID}).json()["id"]
A.post(B + "/api/tasks", json={"title": "Sharpen", "list_id": LID, "parent_id": par})
r = A.post(B + "/api/templates", json={"task_id": par, "name": "Hedge"})
check(r.ok, f"a task template from a task {r.status_code} {r.text[:200]}")
r2 = A.post(B + "/api/lists", json={"name": "Second garden"})
L2 = r2.json()["id"]
r = A.post(B + f"/api/templates/{r.json()['id']}/apply", json={"list_id": L2})
check(r.ok, f"the template applies {r.status_code} {r.text[:200]}")
made = dbx("SELECT id, parent_id, created_by, title FROM tasks WHERE list_id=? ORDER BY id", (L2,))
check(len(made) == 2 and made[0]["title"] == "Cut the hedge" and made[1]["parent_id"] == made[0]["id"]
      and all(m["created_by"] == AID for m in made), f"the template's task with its subtask, mine {[dict(m) for m in made]}")
r = A.get(B + f"/api/tasks/{made[0]['id']}")
check(r.ok and r.json()["title"] == "Cut the hedge", f"the task from the template opens {r.status_code}")

# ---- a person without an organisation: her task lands on top of her inbox, hers
FID, F = freelancer(B, A)
t1 = F.post(B + "/api/tasks", json={"title": "Send the invoice"})
t2 = F.post(B + "/api/tasks", json={"title": "Call the client"})
check(t1.ok and t2.ok, f"a person without an organisation creates tasks {t1.status_code} {t2.status_code}")
r1, r2 = row(t1.json()["id"]), row(t2.json()["id"])
check(r1["created_by"] == FID and r2["created_by"] == FID and r2["list_id"] == r1["list_id"] and r2["sort"] < r1["sort"],
      f"hers, in her inbox, the newer on top {r1['sort']} {r2['sort']}")
check(F.get(B + f"/api/tasks/{r2['id']}").ok and A.get(B + f"/api/tasks/{r2['id']}").status_code in (403, 404),
      "she opens it, the admin of another space does not")

sys.exit(kt.done("p6825_task_insert"))
