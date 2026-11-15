#!/usr/bin/env python3
# kalmido-suite: nodata
# stages-covers: tools/sw_lists.py
"""2.1236.0 (#6199): GitHub's merge queue merges WITHOUT the merge drivers of tools/git_setup.sh. The precache lists of
static/sw.js (SHELL / LAZY / LAZY_CSS) are therefore written one entry per line, sorted, each with a trailing comma
(tools/sw_lists.py), so that plain git merges two packages that add different files without a conflict.
Throwaway git repos without .gitattributes / driver, no server, no network.

- two packages that each add a module at the end of LD_MODS (the usual case) merge clean with plain git; only two files
  sorting into the same gap of a list still conflict (then the tooling's local rebuild with the driver solves it)
- a package adding a module merges clean against main's CACHE line (the train's version cut)
- the real static/sw.js is in that form (tools/sw_lists.py --check)"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

N = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(N)
sys.path.insert(0, N)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from kt import FAILS, OKS, check  # noqa: E402
import sw_lists  # noqa: E402

MODS = [f"m{i:02d}" for i in range(40)]


def git(repo, *a, ok=True):
    p = subprocess.run(["git", "-C", repo, "-c", "user.name=T", "-c", "user.email=t@example.invalid", "-c", "core.hooksPath=/dev/null", *a],
                       capture_output=True, text=True)
    if ok and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)}: {p.stderr.strip()[-300:]}")
    return p


def sw_text(mods, cache=1):
    lazy = [f"/static/js/{m}.js" for m in mods]
    return (f"const CACHE = 'tasks-shell-v{cache}';  // app 1.{cache}.0\n// lists\n" + sw_lists.fmt("SHELL", ["/", "/static/app.css", "/static/js/core.js"])
            + "\n" + sw_lists.fmt("LAZY", lazy) + "\n" + sw_lists.fmt("LAZY_CSS", ["/static/css/a.css"]) + "\nself.x = 1;\n")


def put(repo, text):
    os.makedirs(os.path.join(repo, "static"), exist_ok=True)
    with open(os.path.join(repo, "static", "sw.js"), "w", encoding="utf-8") as f:
        f.write(text)


def merge(ours, theirs, base):
    """plain git merge (no driver) of two changes of static/sw.js on a common base -> (clean?, merged text)"""
    r = tempfile.mkdtemp(prefix="p6199-")
    try:
        git(r, "init", "-q", "-b", "main")
        put(r, base)
        git(r, "add", "-A")
        git(r, "commit", "-qm", "base")
        git(r, "checkout", "-qb", "b")
        put(r, theirs)
        git(r, "commit", "-qam", "theirs")
        git(r, "checkout", "-q", "main")
        put(r, ours)
        git(r, "commit", "-qam", "ours")
        p = git(r, "merge", "-q", "b", ok=False)
        with open(os.path.join(r, "static", "sw.js"), encoding="utf-8") as f:
            return p.returncode == 0, f.read()
    finally:
        shutil.rmtree(r, ignore_errors=True)


def lazy_of(text):
    return re.findall(r"'/static/js/(\w+)\.js'", re.search(r"const LAZY = \[(.*?)\];", text, re.S).group(1))


# two packages, each appends its module to LD_MODS (the lists sorted: they land on different lines)
ok, t = merge(sw_text(MODS + ["notes2"]), sw_text(MODS + ["calx"]), sw_text(MODS))
check(ok and lazy_of(t) == sorted(MODS + ["notes2", "calx"]), f"two packages adding different modules: plain git merges clean\n{t}")
ok, t = merge(sw_text(MODS + ["zz1"]), sw_text(MODS + ["m05b", "m20b"]), sw_text(MODS))
check(ok and lazy_of(t) == sorted(MODS + ["zz1", "m05b", "m20b"]), "one package adds at the end, the other in between: clean")
# the known limit: both add a file into the SAME gap of the sorted list (2 of 59 pairs measured) - a conflict as before;
# the release tooling rebuilds such a branch locally, where tools/sw_lists.py merges it as the driver
ok, t = merge(sw_text(MODS + ["zz1"]), sw_text(MODS + ["zz2"]), sw_text(MODS))
check(not ok, "both into the same gap: still a conflict (documented limit)")
ok, t = merge(sw_text(MODS[1:]), sw_text(MODS + ["new"]), sw_text(MODS))
check(ok and lazy_of(t) == sorted(MODS[1:] + ["new"]), "one package drops a module, the other adds one: clean")
# the train's version cut (CACHE line) against a package that adds a module at the start of SHELL / LAZY
ok, t = merge(sw_text(MODS, cache=2), sw_text(["a0"] + MODS), sw_text(MODS))
check(ok and "tasks-shell-v2" in t and lazy_of(t)[0] == "a0", "CACHE line of the train + a package's new first module: clean")
# the real tree: the form tools/sw_lists.py writes; check_layout refuses the old wrapped form
check(subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sw_lists.py"), "--check"], capture_output=True).returncode == 0,
      "static/sw.js lists: current and one entry per line, sorted")
with open(os.path.join(ROOT, "static", "sw.js"), encoding="utf-8") as f:
    real = f.read()
m = re.search(r"^const LAZY = \[(.*?)\];", real, re.S | re.M)
check(m and m.group(0) == sw_lists.fmt("LAZY", re.findall(r"'(/[^']*)'", m.group(1))), "static/sw.js LAZY as sw_lists.fmt writes it")

print(f"p6199_swlists: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
