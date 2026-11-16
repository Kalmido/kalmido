#!/usr/bin/env python3
# kalmido-suite: nodata
# stages-covers: tools/sw_lists.py
"""2.1258.0 (#6199): GitHub's merge queue merges WITHOUT the merge drivers of tools/git_setup.sh. The precache lists of
static/sw.js (SHELL / LAZY / LAZY_CSS) are therefore written one entry per line, sorted, each with a trailing comma
(tools/sw_lists.py), so that plain git merges two packages that add different files without a conflict.
Throwaway git repos without .gitattributes / driver, no server, no network.

- two packages that each add a module at the end of LD_MODS (the usual case) merge clean with plain git; only two files
  sorting into the same gap of a list still conflict (then the tooling's local rebuild with the driver solves it)
- a package adding a module merges clean against main's CACHE line (the train's version cut); 2.1258.0: the switch to this
  form as well - the first SHELL line (sw_lists.SHELL_HEAD) right below CACHE never changes
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
    # 2.1258.0 (#6199): SHELL right below CACHE, as in the real sw.js (the earlier "// lists" line in between hid the conflict)
    return (f"const CACHE = 'tasks-shell-v{cache}';  // app 1.{cache}.0\n" + sw_lists.fmt("SHELL", ["/", "/static/app.css", "/static/js/core.js"])
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
# 2.1258.0 (#6199): the switch from the wrapped lines to this form must not touch the line below CACHE either - 2.1202 and
# 2.1236 changed it and fell out of the merge queue at every version cut of the train (git: touching lines = one conflict)
def wrapped(name, urls, width=150):
    """the hand-wrapped form before 2.1258 (one line of ~150 chars, continuation indented)"""
    out, line = [], f"const {name} = ["
    for i, u in enumerate(urls):
        item = f"'{u}'" + ("," if i + 1 < len(urls) else "")
        if len(line) + len(item) + 1 > width and line != f"const {name} = [":
            out.append(line.rstrip())
            line = "  " + item
        else:
            line += ("" if line.endswith("[") else " ") + item
    return "\n".join(out + [line + "];"])


SHELL_REAL = list(sw_lists.SHELL_HEAD) + ["/static/icon-512.png", "/static/icon.svg", "/static/badge-96.png"] + [f"/static/js/{m}.js" for m in MODS]
LAZY_REAL = [f"/static/js/l{m}.js" for m in reversed(MODS)]
old_sw = (lambda c: f"// head\nconst CACHE = 'tasks-shell-v{c}';  // app 1.{c}.0\n" + wrapped("SHELL", SHELL_REAL) + "\n// x\n"
          + wrapped("LAZY", LAZY_REAL) + "\n" + wrapped("LAZY_CSS", ["/static/css/a.css"]) + "\nself.x = 1;\n")
switched = sw_lists.rebuild(old_sw(1), ([u for u in SHELL_REAL if u.startswith("/static/js/")], LAZY_REAL, ["/static/css/a.css"]))[0]
check(switched.split("\n")[2] == old_sw(1).split("\n")[2], f"the switch keeps the SHELL line below CACHE: {switched.split(chr(10))[2]}")
ok, t = merge(old_sw(2), switched, old_sw(1))
check(ok and "tasks-shell-v2" in t and "\n  '/static/js/m00.js',\n" in t, f"the switch to the sorted form + the train's CACHE line: clean\n{t[:400]}")
ok, t = merge(sw_text(MODS, cache=2), sw_text(MODS, cache=1).replace("const SHELL = ['/', '/static/app.css',", "const SHELL = ['/',"), sw_text(MODS))
check(not ok, "control: a change on the line right below CACHE does collide with the version cut (why SHELL_HEAD stays)")

# the real tree: the form tools/sw_lists.py writes; check_layout refuses the old wrapped form
check(subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sw_lists.py"), "--check"], capture_output=True).returncode == 0,
      "static/sw.js lists: current and one entry per line, sorted")
with open(os.path.join(ROOT, "static", "sw.js"), encoding="utf-8") as f:
    real = f.read()
m = re.search(r"^const LAZY = \[(.*?)\];", real, re.S | re.M)
check(m and m.group(0) == sw_lists.fmt("LAZY", re.findall(r"'(/[^']*)'", m.group(1))), "static/sw.js LAZY as sw_lists.fmt writes it")
_ln = real.split("\n")
_ci = next(i for i, x in enumerate(_ln) if x.startswith("const CACHE = "))
check(_ln[_ci + 1] == "const SHELL = [" + ", ".join(f"'{u}'" for u in sw_lists.SHELL_HEAD) + ",",
      f"static/sw.js: below CACHE stands the fixed SHELL line (sw_lists.SHELL_HEAD), 2.1258.0: {_ln[_ci + 1][:80]}")

print(f"p6199_swlists: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
