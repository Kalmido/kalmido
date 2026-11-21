#!/usr/bin/env python3
# kalmido-suite: after=p2501_a_nosham nodata
"""#6500: tools/check_devstore.py - every store of the browser that holds something of an account stands in the register
(static/js/icons.js DEV_STORES). Static, no container.
 - the repository: no place outside the register above tools/devstore_baseline.json (exit 0)
 - a new indexedDB.open / caches.open / localStorage / sessionStorage key without an entry is red with the line, exit 1
 - an entry ending in '.' or '-' covers the keys that start with it; a comment line does not count
 - --update only shrinks: a place taken out drops out, nothing is ever added; no baseline file = red
 - the check is a step of the CI lint and kern.md names it
usage: check_devstore_test.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from kt import FAILS, OKS, check

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))


def run(root, *args):
    p = subprocess.run([sys.executable, os.path.join(root, "tools", "check_devstore.py"), "--root", root, *args],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


rc, out = run(ROOT)
check(rc == 0, f"the repository: nothing new outside the register ({out[-400:]})")

d = tempfile.mkdtemp()
try:
    os.makedirs(os.path.join(d, "static", "js"))
    os.makedirs(os.path.join(d, "tools"))
    shutil.copy(os.path.join(ROOT, "tools", "check_devstore.py"), os.path.join(d, "tools"))

    def js(name, src):
        open(os.path.join(d, "static", "js", name), "w", encoding="utf-8").write(src)

    js("icons.js", "const DEV_STORES = [\n  ['ls', 'tasks.', 'view'], ['ss', 'kalmido-tour-', 'view'], ['idb', 'kalmido-start', 'copy'],\n"
                   "  ['cache', 'tasks-shell-', 'view'],\n];\n")
    open(os.path.join(d, "static", "sw.js"), "w").write("const CACHE = 'tasks-shell-v1';\n")
    json.dump({}, open(os.path.join(d, "tools", "devstore_baseline.json"), "w"))
    js("a.js", "indexedDB.open('kalmido-start', 1);\nlocalStorage.setItem('tasks.x', '1');\nsessionStorage.setItem(`kalmido-tour-${n}`, '1');\n"
               "// indexedDB.open('kalmido-other')\n")
    rc, out = run(d)
    check(rc == 0, f"registered stores, a prefix entry and a comment line: green ({out})")
    js("b.js", "const r = indexedDB.open('kalmido-new', 1);\n")
    rc, out = run(d)
    check(rc == 1 and "static/js/b.js:1" in out and "idb 'kalmido-new'" in out, f"a new database without an entry: red with the line ({out})")
    js("b.js", "localStorage.setItem('myapp.secret', '1');\ncaches.open('other');\n")
    rc, out = run(d)
    check(rc == 1 and "ls 'myapp.secret'" in out and "cache 'other'" in out, f"a key outside the prefixes and a new cache: red ({out})")
    open(os.path.join(d, "static", "sw.js"), "w").write("const CACHE = 'shell-v2';\n")
    rc, out = run(d)
    check(rc == 1 and "cache 'shell-v2'" in out, f"the service worker's cache under another name: red ({out})")
    open(os.path.join(d, "static", "sw.js"), "w").write("const CACHE = 'tasks-shell-v2';\n")
    js("b.js", "localStorage.setItem('myapp.secret', '1');\n")
    json.dump({"ls|myapp.secret": 1, "idb|gone": 2}, open(os.path.join(d, "tools", "devstore_baseline.json"), "w"))
    rc, out = run(d)
    check(rc == 0, f"a place of before stays quiet ({out})")
    rc, out = run(d, "--update")
    check(rc == 0 and json.load(open(os.path.join(d, "tools", "devstore_baseline.json"))) == {"ls|myapp.secret": 1},
          f"--update shrinks: a place taken out drops out ({out})")
    js("b.js", "localStorage.setItem('myapp.secret', '1');\nlocalStorage.setItem('myapp.secret', '2');\nlocalStorage.setItem('myapp.more', '2');\n")
    rc, out = run(d, "--update")
    check(rc == 1 and json.load(open(os.path.join(d, "tools", "devstore_baseline.json"))) == {"ls|myapp.secret": 1},
          f"--update never adds a place ({out})")
    os.remove(os.path.join(d, "tools", "devstore_baseline.json"))
    rc, out = run(d)
    check(rc == 1 and "missing" in out, f"no baseline file: red ({out})")
finally:
    shutil.rmtree(d, ignore_errors=True)

# ---------------------------------------------------------------- wired up
ci = open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8").read()
check("python tools/check_devstore.py" in ci, "ci.yml runs tools/check_devstore.py in the lint")
check("check_devstore" in open(os.path.join(ROOT, "docs", "dev", "kern.md"), encoding="utf-8").read(), "kern.md names the check")

print(f"check_devstore: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
