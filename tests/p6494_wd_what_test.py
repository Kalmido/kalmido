#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.1461.0 (#6494): the admin alert names every watchdog part in plain words. Static, no container.
 - every _wd_fail(c, "<what>", ...) in kalmido/ and mcp/ is called with a literal name (a computed one cannot be checked)
 - every such name has its entry in AA_WD_WHAT (kalmido/notify/alerts.py), else the alert shows the raw English name
 - every entry's text is translated in every language of static/i18n/ (not empty)
 - the checker itself: a made-up file with an unknown name and one with a computed name are both found
usage: p6494_wd_what_test.py"""
import ast
import glob
import json
import os

from kt import FAILS, OKS, check

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def wd_what():
    """AA_WD_WHAT read from the source: {what: English text}."""
    tree = ast.parse(open(os.path.join(ROOT, "kalmido/notify/alerts.py"), encoding="utf-8").read())
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "AA_WD_WHAT" for t in n.targets):
            return {k.value: v.args[0].value for k, v in zip(n.value.keys, n.value.values)}
    return {}


def calls(src, name="?"):
    """[(line, literal name or None)] of the _wd_fail calls in one source."""
    out = []
    for n in ast.walk(ast.parse(src, name)):
        if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "_wd_fail":
            a = n.args[1] if len(n.args) > 1 else None
            out.append((n.lineno, a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else None))
    return out


def findings(known, files):
    bad = []
    for fn, src in files:
        for line, what in calls(src, fn):
            if what is None:
                bad.append(f"{fn}:{line} computed name")
            elif what not in known:
                bad.append(f"{fn}:{line} '{what}' has no entry in AA_WD_WHAT")
    return bad


W = wd_what()
check(len(W) > 20 and W.get("invoice series") and W.get("due run of list rule"), f"AA_WD_WHAT read: {len(W)} entries, office and list rules among them")

fake = [("kalmido/x.py", 'def f(c, e, n):\n    _wd_fail(c, "brand new part", 1, e)\n    _wd_fail(c, n, 2, e)\n    _wd_fail(c, "habit", 3, e)\n')]
bad = findings(W, fake)
check(len(bad) == 2 and "brand new part" in bad[0] and "computed" in bad[1], f"the checker finds an unknown and a computed name: {bad}")

files = []
for fn in sorted(glob.glob(os.path.join(ROOT, "kalmido", "**", "*.py"), recursive=True) + glob.glob(os.path.join(ROOT, "mcp", "*.py"))):
    with open(fn, encoding="utf-8") as f:
        files.append((os.path.relpath(fn, ROOT), f.read()))
used = {w for fn, src in files for _, w in calls(src, fn) if w}
check(len(used) > 25, f"the code calls _wd_fail with {len(used)} names")
bad = findings(W, files)
check(not bad, f"every _wd_fail name has a plain-words entry: {bad}")

for p in sorted(glob.glob(os.path.join(ROOT, "static", "i18n", "*.json"))):
    d = json.load(open(p, encoding="utf-8"))
    miss = [t for t in W.values() if not d.get(t)]
    check(not miss, f"{os.path.basename(p)}: every watchdog part name translated {miss}")

print(f"\n{OKS[0]} ok, {len(FAILS)} failed")
raise SystemExit(1 if FAILS else 0)
