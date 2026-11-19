#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.1408.0 (#6831) tools/check_globals.py: the coupling of the web client's global scope only shrinks.
 1. the tool on the web client as it is: the numbers (no base: nothing compared, exit 0); its selftest is green
 2. writes of S: S.key = / +=  / ??= / ++ / delete and a member of it (S.key.x =, S.key[i] =) are writes; reading, a call,
    comparing (==, <=, >=), x.S.key and optional chaining are not
 3. the owner: core.js makes the keys of its `const S = {...}`; a key not in it belongs to the first file that writes it
 4. against a base: a file that newly writes a key another file makes is red (named with the key), a file that no longer
    does is only a note; the count of top-level names is never red
 5. --base with a revision that cannot be read: exit 2 (never a silent green)
usage: python3 tests/p21408_6831_globals_lint_test.py"""
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(N, "..")
sys.path.insert(0, N)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from kt import check, done  # noqa: E402
import check_globals as C  # noqa: E402

TOOL = os.path.join(ROOT, "tools", "check_globals.py")
r = subprocess.run([sys.executable, TOOL], capture_output=True, text=True, timeout=300)
check(r.returncode == 0 and "top-level names" in r.stdout and "foreign writers of S" in r.stdout, "the web client: the numbers " + (r.stdout + r.stderr)[-400:])
r = subprocess.run([sys.executable, TOOL, "--selftest"], capture_output=True, text=True, timeout=60)
check(r.returncode == 0, "selftest: " + (r.stdout + r.stderr)[-800:])
cur = C.collect()
check(cur["names"] > 1000 and len(cur["s_writers"]) > 10, f"the client has many names and foreign writers of S ({cur['names']}, {len(cur['s_writers'])} keys)")

# 2. what is a write
for src, want in [("S.a = 1;", {"a"}), ("S.a += 1;", {"a"}), ("S.a ??= 1;", {"a"}), ("S.a ||= 1;", {"a"}), ("S.a++;", {"a"}), ("--S.a;", {"a"}),
                  ("delete S.a.b;", {"a"}), ("S.a.b = 1;", {"a"}), ("S.a[k] = 1;", {"a"}), ("S.a >>>= 1;", {"a"}),
                  ("if (S.a == 1) f();", set()), ("x = S.a <= 2 || S.a >= 3;", set()), ("S.a.push(1);", set()), ("x.S.a = 1;", set()),
                  ("const f = () => S.a;", set()), ("y = S.a === 1 ? S.b : S.c;", set()), ("const s = 'S.a = 1'; // S.b = 2", set())]:
    got = C.s_writes(src)
    check(got == want, f"writes of {src!r}: {sorted(got)} (want {sorted(want)})")

# 3. the owner
core = "const S = {route: {}, v: 0};\nfunction setRoute(r) { S.route = r; }\n"
m = C.measure({"static/js/core.js": core, "static/js/a.js": "S.extra = 1; S.v = 2;", "static/js/b.js": "S.extra = 2; S.route = {};"})
check(m["s_writers"] == {"v": ["static/js/a.js"], "route": ["static/js/b.js"], "extra": ["static/js/b.js"]},
      f"core.js makes its keys, a key outside it belongs to its first writer {m['s_writers']}")

# 4. against a base
base = C.measure({"static/js/core.js": core, "static/js/a.js": "S.v = 2;"})
bad, fixed = C.compare(m, base)
check(len(bad) == 2 and any("b.js: writes S.route" in x for x in bad) and any("b.js: writes S.extra" in x for x in bad) and not fixed,
      f"a new foreign writer is red, named with the key {bad}")
bad, fixed = C.compare(base, m)
check(not bad and len(fixed) == 2, f"writers gone are a note, not red {bad} {fixed}")
grown = C.measure({"static/js/core.js": core + "function more() {}\nconst x = 1;\n", "static/js/a.js": "S.v = 2;"})
check(grown["names"] > base["names"] and C.compare(grown, base) == ([], []), "more top-level names alone are never red")

# 5. a base that cannot be read
r = subprocess.run([sys.executable, TOOL, "--base", "no-such-revision-6831"], capture_output=True, text=True, timeout=120)
check(r.returncode == 2 and "cannot be read" in r.stdout, f"an unreadable base: exit 2 {r.returncode} {r.stdout[-300:]}")
sys.exit(done("p21408_6831_globals_lint"))
