#!/usr/bin/env python3
# kalmido-suite: after=p2501_a_nosham nodata
"""#7352 (step 4 of audit #5731): tools/check_drop_core.py - no new special way of My tasks beside the drop core. Static,
no container.
 - the repository: no place above tools/drop_core_baseline.json (exit 0)
 - a new moActive() / mseOn() / .mbcol / data-key^="ms:" in a drop path file (dnd.js, a new file) is red with the line, exit 1
 - a comment line or a trailing // comment does not count; the adapter files of ALLOW (mineorder.js ...) stay quiet
 - --update only shrinks: a place taken out lowers the count, a file without places drops out, nothing is ever added
 - (#7519) render.js (allowed: it draws My tasks) may not draw a section's head itself: mseOn( / .mosec / mseHeadHtml /
   mseMenu there are red; moActive() there stays allowed
 - the check is a step of the CI lint and kern.md names it
usage: check_drop_core_test.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from kt import FAILS, OKS, check

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
TOOL = os.path.join(ROOT, "tools", "check_drop_core.py")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import check_drop_core as dc  # noqa: E402


def run(root, *args):
    p = subprocess.run([sys.executable, os.path.join(root, "tools", "check_drop_core.py"), "--root", root, *args],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


# ---------------------------------------------------------------- the repository
rc, out = run(ROOT, "-v")
check(rc == 0, f"the repository: no new special way ({out[-400:]})")
check(set(dc.ALLOW) >= {"static/js/mineorder.js", "static/js/mineboard.js"} and all(dc.ALLOW.values()),
      "the adapter files are allowed, each with its reason")

# ---------------------------------------------------------------- a small invented client
d = tempfile.mkdtemp(prefix="dropcore-")
try:
    os.makedirs(os.path.join(d, "static", "js"))
    os.makedirs(os.path.join(d, "tools"))
    shutil.copy(TOOL, os.path.join(d, "tools"))
    shutil.copy(os.path.join(ROOT, "tools", "lintmsg.py"), os.path.join(d, "tools"))

    def js(name, body):
        with open(os.path.join(d, "static", "js", name), "w", encoding="utf-8") as f:
            f.write(body)
    js("mineorder.js", "const moActive = () => true;\nfunction moPut() { if (moActive() && mseOn()) return 1; }\n")
    js("dnd.js", "const SEL = '#view .ghead[data-key^=\"ms:\"]';\n// moActive() in a comment\nfunction f() { return 1; }  // mseOn() here\n")
    rc, out = run(d, "--update")
    base = json.load(open(os.path.join(d, "tools", "drop_core_baseline.json"), encoding="utf-8"))
    check(rc == 0 and base == {"static/js/dnd.js": 1}, f"first baseline: the selector counts, comments and the adapter not {base} {out}")
    rc, out = run(d)
    check(rc == 0, f"unchanged: green {out}")
    js("dnd.js", "const SEL = '#view .ghead[data-key^=\"ms:\"]';\nfunction f(e) { if (moActive()) return mseDrop(e); }\n")
    rc, out = run(d)
    check(rc == 1 and "static/js/dnd.js:2" in out and "DROP_ADAPTERS" in out, f"a new moActive() in dnd.js: red with the line ({out})")
    rc, _ = run(d, "--update")
    check(rc == 1 and json.load(open(os.path.join(d, "tools", "drop_core_baseline.json"))) == {"static/js/dnd.js": 1},
          "--update never adds a place")
    js("dnd.js", "function f() { return 1; }\n")
    js("palette.js", "function nudge() { return document.querySelector('.kcol:not(.mbcol)'); }\n")
    rc, out = run(d)
    check(rc == 1 and "static/js/palette.js" in out, f"a new file with .mbcol: red ({out})")
    js("palette.js", "function nudge() { return 1; }\n")
    js("render.js", "function rv() { return moActive() ? 1 : 0; }\n")
    rc, out = run(d)
    check(rc == 0, f"#7519: render.js draws My tasks: moActive() there stays allowed ({out})")
    js("render.js", "function rv(g) { return g.mosec ? mseHeadHtml(g) : ''; }\n")
    rc, out = run(d)
    check(rc == 1 and "static/js/render.js:1" in out and "sh_head" in out, f"#7519: a section's head drawn by render.js itself: red ({out})")
    js("render.js", "function rv(g) { return sh_head(g).menu; }\n")
    rc, out = run(d, "--update")
    check(rc == 0 and json.load(open(os.path.join(d, "tools", "drop_core_baseline.json"))) == {},
          f"--update shrinks: the place taken out drops out ({out})")
    os.remove(os.path.join(d, "tools", "drop_core_baseline.json"))
    rc, out = run(d)
    check(rc == 1 and "missing" in out, f"no baseline file: red ({out})")
finally:
    shutil.rmtree(d, ignore_errors=True)

check(dc.code_part("  // moActive()") == "" and dc.code_part("x(); // mseOn()") == "x();" and "mbcol" in dc.code_part("a('.mbcol')"),
      "comment lines and trailing comments do not count, the code does")

# ---------------------------------------------------------------- wired up
ci = open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8").read()
check("python tools/check_drop_core.py" in ci, "ci.yml runs tools/check_drop_core.py in the lint")
check("check_drop_core" in open(os.path.join(ROOT, "docs", "dev", "kern.md"), encoding="utf-8").read(), "kern.md names the check")

print(f"check_drop_core: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
