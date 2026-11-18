#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.1358.0 (#6825) tools/check_task_insert.py: a new task is written only by task_insert() of kalmido/tasks/repo.py.
 1. the repository: no own INSERT INTO tasks outside repo.py, the baseline is empty, check_layout.py runs the check
 2. red: INSERT INTO tasks( in one line, split over lines, with a blank before the bracket, in lower case, INSERT ... SELECT
 3. green: other tables (task_tags, tasks_x), reading, UPDATE / DELETE, a schema name before tasks is no own insert either way
 4. the exception: `task-insert-ok: <reason>` on the line of the INSERT; without a reason or on another line still red
 5. the ratchet: a file above its baseline is red, at or below it quiet; repo.py itself never counts
 6. 2.1389.0 (#6988): the exceptions are counted too (baseline "_ok"): a new task-insert-ok is red until the baseline holds it
usage: python3 tests/p6825_task_insert_lint_test.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

N = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(N, "..")
sys.path.insert(0, N)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from kt import check, done  # noqa: E402
import check_task_insert as cti  # noqa: E402

# 1. the repository
r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check_task_insert.py")], capture_output=True, text=True, timeout=300)
check(r.returncode == 0, "the server package: no own INSERT INTO tasks: " + (r.stdout + r.stderr)[-800:])
check(cti.counts() == {}, f"nothing left over: {cti.counts()}")
check(cti.load_baseline() == {}, f"the baseline is empty: {cti.load_baseline()}")
check(cti.counts(marked=True) == cti.load_ok_baseline(), f"#6988: the exceptions are the baseline's: {cti.counts(marked=True)} {cti.load_ok_baseline()}")
check("check_task_insert.errors()" in open(os.path.join(ROOT, "tools", "check_layout.py"), encoding="utf-8").read(),
      "check_layout.py (CI lint, Mac lint) runs the check")
REPO = open(os.path.join(ROOT, "kalmido", "tasks", "repo.py"), encoding="utf-8").read()
check(any("insert_id(" in REPO.split("\n")[n - 1] for n in cti.scan(REPO)), "repo.py holds the one insert (and is left out of the count)")

# 2. red
RED = {
    "one line": 'tid = insert_id(c, "INSERT INTO tasks(list_id,title,sort) VALUES(?,?,?)", (lid, t, 0))',
    "split": 'c.execute("""INSERT INTO\n    tasks(list_id,title) VALUES(?,?)""", (lid, t))',
    "blank": 'c.execute("INSERT INTO tasks (list_id,title) VALUES(?,?)", (lid, t))',
    "lower": 'c.execute("insert into tasks(list_id,title) values(?,?)", (lid, t))',
    "select": 'c.execute("INSERT INTO tasks SELECT * FROM tasks WHERE id=?", (tid,))',
    "f-string": 'insert_id(c, f"INSERT INTO tasks({",".join(cols)}) VALUES({q})", vals)',
}
for name, src in RED.items():
    check(len(cti.scan(src)) == 1, f"red: {name}: {cti.scan(src)}")
check(cti.scan("x = 1\n\n" + RED["one line"]) == [3], "the finding names its line")

# 3. green
GREEN = {
    "task_tags": 'c.execute("INSERT INTO task_tags(task_id,tag) VALUES(?,?)", (t, g))',
    "tasks_x": 'c.execute("INSERT INTO tasks_archive(id) VALUES(?)", (t,))',
    "schema": 'c.execute("INSERT INTO tasks.archive(id) VALUES(?)", (t,))',
    "read": 'c.execute("SELECT * FROM tasks WHERE id=?", (t,))',
    "update": 'c.execute("UPDATE tasks SET title=? WHERE id=?", (x, t))',
    "delete": 'c.execute("DELETE FROM tasks WHERE id=?", (t,))',
    "helper": 'tid = task_insert(c, uid, lid, title=t)',
}
for name, src in GREEN.items():
    check(cti.scan(src) == [], f"green: {name}: {cti.scan(src)}")

# 4. the exception
ok = RED["one line"] + "  # task-insert-ok: raw copy inside a migration fragment"
check(cti.scan(ok) == [], "task-insert-ok with a reason: no finding")
check(len(cti.scan(RED["one line"] + "  # task-insert-ok:")) == 1, "task-insert-ok without a reason: still red")
check(len(cti.scan("# task-insert-ok: a reason on another line\n" + RED["one line"])) == 1, "task-insert-ok on another line: still red")

# 5. the ratchet on a copy of a small tree
tmp = tempfile.mkdtemp()
try:
    os.makedirs(os.path.join(tmp, "kalmido", "tasks"))
    os.makedirs(os.path.join(tmp, "kalmido", "office"))
    shutil.copy(os.path.join(ROOT, "kalmido", "tasks", "repo.py"), os.path.join(tmp, "kalmido", "tasks", "repo.py"))
    with open(os.path.join(tmp, "kalmido", "office", "x.py"), "w", encoding="utf-8") as f:
        f.write(RED["one line"] + "\n" + RED["blank"] + "\n")
    rel = os.path.join("kalmido", "office", "x.py")
    check(cti.counts(tmp) == {rel: 2}, f"the count per file, repo.py left out: {cti.counts(tmp)}")
    e = cti.errors(tmp, base={})
    check(len(e) == 1 and rel in e[0] and "task_insert()" in e[0] and "kalmido/tasks/repo.py" in e[0], f"a new file is red, with the way out: {e}")
    check(cti.errors(tmp, base={rel: 2}) == [] and cti.errors(tmp, base={rel: 3}) == [], "at or below its baseline: quiet")
    check(len(cti.errors(tmp, base={rel: 1})) == 1, "above its baseline: red")
    # 6. the exceptions (#6988)
    oks = os.path.join("kalmido", "office", "y.py")
    with open(os.path.join(tmp, oks), "w", encoding="utf-8") as f:
        f.write(ok + "\n")
    check(cti.counts(tmp) == {rel: 2} and cti.counts(tmp, marked=True) == {oks: 1}, f"#6988: the exception counted on its own: {cti.counts(tmp, marked=True)}")
    e = cti.errors(tmp, base={rel: 2}, ok_base={})
    check(len(e) == 1 and oks in e[0] and "task-insert-ok" in e[0] and "--write" in e[0], f"#6988: a new exception is red, with the way out: {e}")
    check(cti.errors(tmp, base={rel: 2}, ok_base={oks: 1}) == [], "#6988: an exception in the baseline: quiet")
    check(len(cti.errors(tmp, base={rel: 2}, ok_base={oks: 0})) == 1, "#6988: above its baseline: red")
finally:
    shutil.rmtree(tmp)
check(json.load(open(cti.BASELINE, encoding="utf-8")).get("_note", "").startswith("2.1358.0 (#6825)"), "the baseline names its rule")

sys.exit(done("p6825_task_insert_lint"))
