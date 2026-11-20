#!/usr/bin/env python3
"""2.1458.0 (#6593, audit #4808 T21): the format number of the account export (UMZ_V, kalmido/admin/acctexport.py) rises when a
table of the account export loses or renames a column.

The export takes every column of its tables (SELECT *), the import takes the columns it has (admin/acctimport.py umz_row). A
column that is gone or has a new name changes what a file means: an older server reads a newer file wrongly, a newer server an
older one. UMZ_V stood at 1 from 2.73 on although columns went (lists.archived, contacts.search ...); the import refuses a file
whose number is above its own, so the number has to say when the meaning changed.

Read (static, no database): kalmido/core/schema.py + the fragments of migrations.d - every ALTER TABLE ... DROP COLUMN and
RENAME COLUMN on a table of the account export (the tables of check_export_tables.py acct_tables: the export's queries, the
register of the core, the built parts). What is there today stands in tools/umz_v_steps.json ({"umz_v": n, "known": [...]}).

  a new step ("<file>: <table>.<column> drop | rename")   red while UMZ_V is not above the recorded number: raise UMZ_V
                                                           (and let the import read the old column), then --update
  UMZ_V other than the recorded number                     red: --update records it (never lower)
  a recorded step that is gone                             a note

usage: python3 tools/check_umz_v.py [-v] [--update]      exit 1 on a finding; --update records UMZ_V and today's steps
Standard library only.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from check_migrations import fragments  # noqa: E402

STEPS = os.path.join("tools", "umz_v_steps.json")
ACCT = os.path.join("kalmido", "admin", "acctexport.py")
ALTER = re.compile(r"[\"';]\s*ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?\"?(\w+)\"?\s+([^;\"]*)", re.I)
DROP_COL = re.compile(r"\bDROP\s+(?:COLUMN\s+)?(?:IF\s+EXISTS\s+)?\"?(\w+)\"?", re.I)
RENAME_COL = re.compile(r"\bRENAME\s+(?:COLUMN\s+)?\"?(\w+)\"?\s+TO\s+\"?(\w+)\"?", re.I)
NOT_COL = {"CONSTRAINT", "DEFAULT", "NOT", "IDENTITY", "EXPRESSION", "TRIGGER", "POLICY", "INDEX"}


def sources(root=ROOT):
    """[(name, text)] of schema.py and the fragments (name = the file name, no folder: moving a file is no new step)."""
    out = []
    for p in [os.path.join(root, "kalmido", "core", "schema.py")] + fragments(root):
        with open(p, encoding="utf-8") as f:
            out.append((os.path.basename(p), f.read()))
    return out


def steps(srcs, tables):
    """{"<file>: <table>.<column> drop|rename"} of every DROP COLUMN / RENAME COLUMN on one of tables. A statement starts a
    string (or follows a ';'): the words in a docstring's sentence are no step, nor an SQL comment; ALTER COLUMN ...
    DROP DEFAULT / DROP NOT NULL / DROP CONSTRAINT neither."""
    out = set()
    for name, raw in srcs:
        src = re.sub(r"--[^\n]*", "", raw)
        for m in ALTER.finditer(src):
            table, rest = m.group(1), m.group(2)
            if table not in tables:
                continue
            for part in re.split(r",(?![^()]*\))", rest):
                p = part.strip()
                if re.match(r"ALTER\s", p, re.I):
                    continue
                d = re.match(r"DROP\s", p, re.I) and DROP_COL.match(p)
                if d and d.group(1).upper() not in NOT_COL:
                    out.add(f"{name}: {table}.{d.group(1)} drop")
                r = RENAME_COL.match(p)
                if r and not re.match(r"RENAME\s+TO\s", p, re.I) and r.group(1).upper() != "CONSTRAINT":
                    out.add(f"{name}: {table}.{r.group(1)} rename")
    return out


def umz_v(root=ROOT):
    with open(os.path.join(root, ACCT), encoding="utf-8") as f:
        m = re.search(r"^UMZ_V\s*=\s*(\d+)", f.read(), re.M)
    return int(m.group(1)) if m else 0


def recorded(root=ROOT):
    try:
        with open(os.path.join(root, STEPS), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return 0, set()
    return int(d.get("umz_v") or 0), set(d.get("known") or ())


def findings(now, v, rec_v, known):
    """(red lines, notes) for today's steps now and UMZ_V v against the record (rec_v, known)."""
    new = sorted(now - known)
    bad = []
    if new and v <= rec_v:
        bad += [f"check_umz_v: {s}: a table of the account export loses or renames a column - raise UMZ_V in {ACCT} (and let the "
                "import read the old column), then python3 tools/check_umz_v.py --update" for s in new]
    elif v < rec_v:
        bad.append(f"check_umz_v: UMZ_V is {v}, {STEPS} records {rec_v}: the format number never goes down")
    elif v != rec_v or new:
        bad.append(f"check_umz_v: UMZ_V is {v}, {STEPS} records {rec_v}{' and not ' + ', '.join(new) if new else ''}: "
                   "python3 tools/check_umz_v.py --update")
    notes = [f"note: {s} is recorded in {STEPS} but no longer in the code (--update drops it)" for s in sorted(known - now)]
    return bad, notes


def main(argv, root=ROOT):
    from check_export_tables import acct_tables
    now, v = steps(sources(root), acct_tables(root)), umz_v(root)
    rec_v, known = recorded(root)
    bad, notes = findings(now, v, rec_v, known)
    if "--update" in argv:
        if now - known and v <= rec_v:
            for b in bad:
                print(b)
            print("check_umz_v: --update records nothing until UMZ_V is raised")
            return 1
        with open(os.path.join(root, STEPS), "w", encoding="utf-8") as f:
            json.dump({"umz_v": v, "known": sorted(now)}, f, indent=1)
            f.write("\n")
        print(f"check_umz_v: recorded UMZ_V {v} and {len(now)} step(s)")
        return 0
    for x in bad + notes:
        print(x)
    if "-v" in argv or bad:
        print(f"check_umz_v: UMZ_V {v}, {len(now)} column step(s) on tables of the account export, {len(bad)} finding(s)")
    return 1 if bad else 0


LINT_WHY = "a file of the account export means something else once a column is gone or renamed; only UMZ_V tells the import"
LINT_INSTEAD = "raise UMZ_V in kalmido/admin/acctexport.py, read the old column in the import, record it with --update"


if __name__ == "__main__":
    import lintmsg  # tools/ is the script's folder, so it is on the path
    with lintmsg.red_hint("check_umz_v", LINT_WHY, LINT_INSTEAD):
        sys.exit(main(sys.argv[1:]))
