#!/usr/bin/env python3
# kalmido-suite: after=p2501_a_nosham nodata
"""#6500: tools/check_devstore.py - every store of the browser that holds something of an account stands in the register
(static/js/icons.js DEV_STORES). Static, no container.
 - the repository: no place outside the register above tools/devstore_baseline.json (exit 0)
 - a new indexedDB.open / caches.open / localStorage / sessionStorage key without an entry is red with the line, exit 1
 - an entry ending in '.' or '-' covers the keys that start with it; a comment line does not count
 - --update only shrinks: a place taken out drops out, nothing is ever added; no baseline file = red
 - (#7595) the second places of one store (a 4th field in DEV_STORES: tasks.outbox feed of kalmido-outbox, tasks.cache
   fallback of kalmido-start) are written only by their owner: a write elsewhere (localStorage.setItem / removeItem, LS.set /
   LS.del) is red with the line, a comment line does not count; a role without an owner (and an owner without a role) is red
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

    REG = ("const DEV_STORES = [\n  ['ls', 'tasks.', 'view'], ['ss', 'kalmido-tour-', 'view'], ['idb', 'kalmido-start', 'copy'],\n"
           "  ['ls', 'tasks.outbox', 'own', 'feed of kalmido-outbox'], ['ls', 'tasks.cache', 'copy', 'fallback of kalmido-start'],\n"
           "  ['cache', 'tasks-shell-', 'view'],\n];\n")
    js("icons.js", REG)
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
    # ---- (#7595) the owner of a second place
    json.dump({}, open(os.path.join(d, "tools", "devstore_baseline.json"), "w"))
    js("b.js", "")
    js("core.js", "function startSave(now) {\n  LS.set('cache', S.lpCache);\n}\nfunction outSave(fn) {\n  fn(); LS.set('outbox', OUT.q);\n}\n"
                  "function obxFeedSet(l) {\n  localStorage.setItem('tasks.outbox', JSON.stringify(l));\n}\n")
    js("offcache.js", "function oc_lsDrop(raw) {\n  localStorage.removeItem('tasks.cache');\n}\n")
    rc, out = run(d)
    check(rc == 0, f"#7595: the owners write their places: green ({out})")
    js("b.js", "function lpCacheNow() {\n  // LS.set('cache', S.lpCache) was here\n  if (x) LS.set('cache', S.lpCache);\n}\n")
    rc, out = run(d)
    check(rc == 1 and "static/js/b.js:3: 'tasks.cache' written outside its owner (in lpCacheNow" in out and "b.js:2" not in out,
          f"#7595: the start state's fallback written outside its owner: red with the line, the comment line not ({out})")
    js("b.js", "const x = 1;\nfunction obxAdopt() {\n  localStorage.removeItem(`tasks.outbox`);\n}\n")
    js("offcache.js", "function oc_write() {\n  LS.del('outbox');\n}\n")
    rc, out = run(d)
    check(rc == 1 and "static/js/b.js:3: 'tasks.outbox'" in out and "static/js/offcache.js:2: 'tasks.outbox'" in out,
          f"#7595: the feed written outside its owner (a template literal, LS.del): red ({out})")
    js("b.js", ""); js("offcache.js", "")
    js("icons.js", REG.replace("['ls', 'tasks.cache', 'copy', 'fallback of kalmido-start']", "['ls', 'tasks.cache', 'copy']")
                      .replace("['cache', 'tasks-shell-', 'view']", "['ls', 'tasks.wko', 'copy', 'fallback of kalmido-wiki'], ['cache', 'tasks-shell-', 'view']"))
    rc, out = run(d)
    check(rc == 1 and "'tasks.wko' has a role in DEV_STORES but no owner" in out and "OWNERS names 'tasks.cache', the register gives it no role" in out,
          f"#7595: a role without an owner and an owner without a role: red ({out})")
    js("icons.js", REG)
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
