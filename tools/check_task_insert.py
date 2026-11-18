#!/usr/bin/env python3
"""2.1358.0 (#6825): a new task is written in ONE place - task_insert() of kalmido/tasks/repo.py.

Before, 26 files had their own `INSERT INTO tasks(...)` (39 of them), each with its own idea of the columns, the sort order
and the defaults a new task needs; a new task from a mail, a template, an agent, the office or the family came out a little
different each time. They all call task_insert now. This ratchet counts the writes of new task rows (INSERT INTO tasks, also
split over lines, in any case) per file in kalmido/**/*.py outside kalmido/tasks/repo.py and compares them with
tools/task_insert_baseline.json: a file may have as many as its baseline says or fewer, never more, and a file not in the
baseline has none. The baseline only shrinks (--write after moving a file onto task_insert); today it is empty.

Not counted: other tables whose name starts with tasks (task_*, tasks_x), reading (SELECT ... FROM tasks), UPDATE / DELETE.
Exception: the comment `task-insert-ok: <reason>` (at least a few words) on the line of the INSERT, for a write that
cannot go through task_insert (a raw copy in a migration that must not load the app). 2.1389.0 (#6988): the exceptions are
counted too, per file under "_ok" of the baseline: a new one is red until --write puts it into the baseline in the same
commit, so every exception shows in the diff and its review instead of loosening the rule unseen.

Runs inside tools/check_layout.py (CI lint, Mac lint) and on its own:

usage: python3 tools/check_task_insert.py [--write]      exit code 1 on a hit; --write sets the baseline to today's counts
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULE = os.path.join("kalmido", "tasks", "repo.py")
BASELINE = os.path.join(ROOT, "tools", "task_insert_baseline.json")
INS = re.compile(r"\bINSERT\s+INTO\s+tasks\b(?![\w.])", re.I)
OK = re.compile(r"task-insert-ok:\s*[A-Za-z][\w ,.;()'-]{9,}")


def scan(src, marked=False):
    """The line numbers of the own task inserts in the source src (without the ones marked task-insert-ok); marked=True
    (2.1389.0, #6988): only the ones marked task-insert-ok."""
    lines = src.split("\n")
    out = []
    for m in INS.finditer(src):
        n = src.count("\n", 0, m.start())
        if bool(OK.search(lines[n])) == marked:
            out.append(n + 1)
    return out


def counts(root=ROOT, marked=False):
    """{path: number of own task inserts} for every file of kalmido/ with at least one; marked=True: the exceptions."""
    out = {}
    for p in sorted(glob.glob(os.path.join(root, "kalmido", "**", "*.py"), recursive=True)):
        rel = os.path.relpath(p, root)
        if rel == RULE:
            continue
        with open(p, encoding="utf-8") as f:
            n = len(scan(f.read(), marked))
        if n:
            out[rel] = n
    return out


def _load():
    try:
        with open(BASELINE, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}


def load_baseline():
    return {k: v for k, v in _load().items() if not k.startswith("_")}


def load_ok_baseline():
    """2.1389.0 (#6988): {path: number of task-insert-ok exceptions} the baseline allows."""
    return dict(_load().get("_ok") or {})


def errors(root=ROOT, base=None, ok_base=None):
    base = load_baseline() if base is None else base
    ok_base = load_ok_baseline() if ok_base is None else ok_base
    return [f"{p}: {n} own INSERT INTO tasks, baseline {base.get(p, 0)} - create the task with task_insert() of "
            f"kalmido/tasks/repo.py (one place for the required columns, sort, defaults) or mark a write that cannot go "
            f"through it with 'task-insert-ok: <reason>'" for p, n in sorted(counts(root).items()) if n > base.get(p, 0)] + \
           [f"{p}: {n} exception(s) 'task-insert-ok', baseline {ok_base.get(p, 0)} - an exception is counted (#6988): use "
            f"task_insert() of kalmido/tasks/repo.py, or put it into the baseline with 'python3 tools/check_task_insert.py "
            f"--write' in the same commit" for p, n in sorted(counts(root, marked=True).items()) if n > ok_base.get(p, 0)]


def write():
    data = {"_note": "2.1358.0 (#6825): own INSERT INTO tasks per file (tools/check_task_insert.py); may only go down. "
                     "2.1389.0 (#6988): _ok = the task-insert-ok exceptions per file, counted the same way."}
    data.update(counts())
    ok = counts(marked=True)
    if ok:
        data["_ok"] = ok
    with open(BASELINE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=0, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    if "--write" in sys.argv[1:]:
        write()
        sys.exit(0)
    errs = errors()
    for e in errs:
        print(e)
    sys.exit(1 if errs else 0)
