#!/usr/bin/env python3
"""2.1238.0 (#6161): write entries in the browser follow ONE rule - canWrite() of static/js/workspace.js (docs/dev/kern.md,
"Who may write: the client").

Before, every area decided with a check of its own (`role === 'edit'`, `o.role === 'readonly'`, a list of read-only roles)
whether to show New, plus, upload, drag, import, finalise, save - or forgot it. This check counts those own role checks
per file in static/js/*.js (outside workspace.js, where the rule lives) and compares them with tools/canwrite_baseline.json:
a file may have as many as its baseline says or fewer, never more, and a file not in the baseline has none. So a new
write entry asks canWrite(x) instead of comparing roles by hand; the baseline only shrinks (--write after moving a file
onto canWrite).

Counted: a comparison of a role with one of the object / organisation write roles, e.g. `role === 'edit'`,
`n.role !== 'view'`, `o.role == 'readonly'`, `r === 'owner'` with a name ending in role / r.
Exception: the comment `canwrite-ok: <reason>` (at least a few words) on the same line, for a role check that does not
decide about writing (a label, a sort order, an admin menu).

Runs inside tools/check_layout.py (CI lint, Mac lint) and on its own:

usage: python3 tools/check_canwrite.py [--write]      exit code 1 on a hit; --write sets the baseline to today's counts
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULE = os.path.join("static", "js", "workspace.js")
BASELINE = os.path.join(ROOT, "tools", "canwrite_baseline.json")
ROLECMP = re.compile(r"\b(?:\w*role|r)\s*[!=]==?\s*['\"](?:edit|view|readonly|owner|manage)['\"]"
                     r"|['\"](?:edit|view|readonly|owner|manage)['\"]\s*[!=]==?\s*(?:[\w.?]*\.)?\w*role\b")
OK = re.compile(r"canwrite-ok:\s*[A-Za-z][\w ,.;()'-]{9,}")


def counts():
    """{path: number of own role checks} for every file in static/js with at least one."""
    out = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "static", "js", "*.js"))):
        rel = os.path.relpath(p, ROOT)
        if rel == RULE:
            continue
        with open(p, encoding="utf-8") as f:
            n = sum(len(ROLECMP.findall(ln)) for ln in f if not OK.search(ln))
        if n:
            out[rel] = n
    return out


def load_baseline():
    try:
        with open(BASELINE, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    except OSError:
        return {}


def errors():
    base, now = load_baseline(), counts()
    return [f"{p}: {n} own role check(s) for writing, baseline {base.get(p, 0)} - ask canWrite(x) of static/js/workspace.js "
            f"(docs/dev/kern.md, 'Who may write: the client') or mark a check that does not decide about writing with "
            f"'canwrite-ok: <reason>'" for p, n in sorted(now.items()) if n > base.get(p, 0)]


def write():
    data = {"_note": "2.1238.0 (#6161): own role checks per file (tools/check_canwrite.py); may only go down."}
    data.update(counts())
    with open(BASELINE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=0, sort_keys=True)
        f.write("\n")


LINT_WHY = "an area that decides with its own role check shows New / upload / save to people who may not write, or forgets it"
LINT_INSTEAD = "canWrite() of static/js/workspace.js (docs/dev/kern.md, 'Who may write: the client')"


if __name__ == "__main__":
    import lintmsg  # tools/ is the script's folder, so it is on the path
    with lintmsg.red_hint("check_canwrite", LINT_WHY, LINT_INSTEAD):
        if "--write" in sys.argv[1:]:
            write()
            sys.exit(0)
        errs = errors()
        for e in errs:
            print(e)
        sys.exit(1 if errs else 0)
