#!/usr/bin/env python3
# kalmido-suite: nodata
"""#7143 the lint says the cause and the right way; suppressions only with a reason and only fewer. No container:
 1. tools/check_suppress.py: the same markers as the baseline = green; one more noqa: BLE001 (even with a reason) = red;
    a new marker without its reason = red also for a kind whose number may rise (E402); with the reason = a notice only
 2. a reason is two words beside the marker - a version mark alone is none; a docstring that names a marker is no marker;
    JavaScript // eslint-disable and /* sprung-ok */ count
 3. fewer = green with a notice; --update lowers the baseline and never raises it (a rise stays red after --update)
 4. tools/check_rules.py: os.environ outside core/env.py, a starter helper defined twice = red with
    the rule's Why / Instead; a writing api() call in static/js and the total of version marks = a notice only; inside core/env.py = no finding
 5. every red message carries Why / Instead / "Do not suppress it"; tools/lintmsg.red_hint prints nothing on green
 6. every tools/check_*.py says Why / Instead (lintmsg); ci.yml runs both new checks with --notice (a rise there is a notice:
    the totals move with every package merged meanwhile; red per change is tools/pr_lint.py, suite p2593_l_prlint)
usage: python3 tests/p21403_c_suppress_test.py"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

N = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(N, ".."))
sys.path.insert(0, N)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from kt import FAILS, OKS, check  # noqa: E402
import lintmsg  # noqa: E402

SUP = os.path.join(ROOT, "tools", "check_suppress.py")
RUL = os.path.join(ROOT, "tools", "check_rules.py")
NOT = "Do not suppress it and do not build around it"


def run(tool, root, *flags):
    r = subprocess.run([sys.executable, tool, "--root", root, *flags], capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def tree(files):
    d = tempfile.mkdtemp(prefix="p21403c-")
    for rel, text in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
    os.makedirs(os.path.join(d, "tools"), exist_ok=True)
    return d


def put(d, rel, text):
    with open(os.path.join(d, rel), "w", encoding="utf-8") as f:
        f.write(text)


def baseline_of(d, tool, name):
    """Writes the start baseline of TOOL for tree D (what the package did once for the repo)."""
    mod = __import__(tool)
    now = mod.counts(mod.places(d)) if tool == "check_suppress" else mod.counts(d)[0]
    lintmsg.save(os.path.join(d, "tools", name), "test", now)


def total(d, name, rule):
    return lintmsg.load(os.path.join(d, "tools", name)).get(rule, {}).get("total", 0)


# ---- 1. check_suppress: the ratchet per kind and the reason
PY0 = ('"""Names # noqa: BLE001 in a docstring - no marker."""\n'
       "try:\n    x = 1\nexcept Exception:  # noqa: BLE001 -- the worker never dies on one run\n    x = 0\n"
       "import os  # noqa: E402 -- the path is set above\n")
JS0 = "function f() {\n  el.scrollIntoView();  /* sprung-ok: the person asked for it */\n}\n"
d = tree({"kalmido/a.py": PY0, "static/js/x.js": JS0})
try:
    baseline_of(d, "check_suppress", "suppress_baseline.json")
    check(total(d, "suppress_baseline.json", "noqa:BLE001") == 1, "the docstring's '# noqa: BLE001' is no marker, the comment is one")
    check(total(d, "suppress_baseline.json", "mark:sprung-ok") == 1, "a /* sprung-ok: */ comment in JavaScript counts")
    rc, out = run(SUP, d)
    check(rc == 0, f"the same markers as the baseline: green ({out[-300:]})")

    put(d, "kalmido/b.py", "try:\n    y = 1\nexcept Exception:  # noqa: BLE001 -- a hint must never break the page\n    y = 0\n")
    rc, out = run(SUP, d)
    check(rc == 1 and "'noqa:BLE001' markers: 2, the baseline allows 1" in out and "kalmido/b.py 1 (was 0)" in out,
          f"one more noqa: BLE001, even with its reason: red, the file named ({out[-400:]})")
    check("Why:" in out and "Instead:" in out and NOT in out, f"the red message says why, what instead and not to suppress: {out[-400:]}")

    put(d, "kalmido/b.py", "import sys  # noqa: E402\n")
    rc, out = run(SUP, d)
    check(rc == 1 and "new 'noqa:E402' without its reason" in out, f"a new E402 without its reason: red ({out[-300:]})")
    put(d, "kalmido/b.py", "import sys  # noqa: E402  2.755.0 (#5294)\n")
    rc, out = run(SUP, d)
    check(rc == 1 and "without its reason" in out, f"a version mark is no reason: red ({out[-300:]})")
    put(d, "kalmido/b.py", "import sys  # noqa: E402 -- tools/ goes on the path above\n")
    rc, out = run(SUP, d)
    check(rc == 0 and "notice (not red yet): 'noqa:E402' markers: 2" in out,
          f"a new E402 with its reason: a notice only, E402 may rise ({out[-300:]})")
    os.remove(os.path.join(d, "kalmido/b.py"))

    put(d, "static/js/y.js", "// eslint-disable-next-line no-new\nnew Thing();\n")
    rc, out = run(SUP, d)
    check(rc == 1 and "'eslint-disable' markers: 1, the baseline allows 0" in out and "without its reason" in out,
          f"a new eslint-disable without a reason: red twice over ({out[-300:]})")
    put(d, "static/js/y.js", "// eslint-disable-next-line no-new -- the instance registers itself\nnew Thing();\n")
    rc, out = run(SUP, d)
    check(rc == 1 and "'eslint-disable' markers: 1" in out and "new 'eslint-disable' without" not in out, f"with its reason still red: eslint-disable may not rise ({out[-300:]})")
    rc, out = run(SUP, d, "--notice")
    check(rc == 0 and "notice (not red yet): 'eslint-disable' markers: 1" in out,
          f"--notice (the lint job): the same rise is a notice, red is the per-change check of pr_lint ({out[-300:]})")
    os.remove(os.path.join(d, "static/js/y.js"))

    # #7176: the file-wide and the other tools' markers count too, and a block comment over several lines is read
    for rel, text, kind in (("kalmido/c.py", "# ruff: noqa\nx = 1\n", "noqa:file"),
                            ("kalmido/c.py", "# flake8: noqa: E501\nx = 1\n", "noqa:file"),
                            ("kalmido/c.py", "from calc import dec  # type: ignore[misc]\n", "type-ignore"),
                            ("kalmido/c.py", "exec(code)  # nosec\n", "nosec"),
                            ("static/js/z.js", "// @ts-nocheck\nlet a = 1;\n", "ts-ignore"),
                            ("static/js/z.js", "const t = 'image/*';\n/*\n eslint-disable no-new\n*/\nnew Thing();\n",
                             "eslint-disable")):
        put(d, rel, text)
        rc, out = run(SUP, d)
        check(rc == 1 and f"'{kind}' markers: 1, the baseline allows 0" in out and f"new '{kind}' without" in out,
              f"#7176: {text.strip()[:40]!r} counts as '{kind}' without a reason: red ({out[-300:]})")
        os.remove(os.path.join(d, rel))
    put(d, "static/js/z.js", "const t = 'image/*';\nlet a = 1;  // the accept list\n")
    rc, out = run(SUP, d)
    check(rc == 0, f"#7176: a '/*' inside a string opens no block comment: green ({out[-300:]})")
    os.remove(os.path.join(d, "static/js/z.js"))

    # ---- 3. fewer: green with a notice, --update lowers, never raises
    put(d, "kalmido/a.py", "x = 1\nimport os  # noqa: E402 -- the path is set above\n")
    rc, out = run(SUP, d)
    check(rc == 0 and "lower it" in out, f"one fewer: green, the notice says to lower the baseline ({out[-300:]})")
    rc, out = run(SUP, d, "--update")
    check(rc == 0 and total(d, "suppress_baseline.json", "noqa:BLE001") == 0, f"--update lowered BLE001 to 0 ({out[-300:]})")
    put(d, "kalmido/a.py", PY0)
    rc, out = run(SUP, d, "--update")
    check(rc == 1 and total(d, "suppress_baseline.json", "noqa:BLE001") == 0,
          f"--update never raises: the BLE001 back is red and the baseline stays 0 ({out[-300:]})")
finally:
    shutil.rmtree(d, ignore_errors=True)

# lowered() itself: a rule above its number keeps the old entry, a rule the baseline did not hold is not added
b = {"a": {"total": 2, "files": {"x": 2}}, "b": {"total": 3, "files": {"x": 3}}}
n = {"a": {"total": 1, "files": {"y": 1}}, "b": {"total": 4, "files": {"x": 4}}, "c": {"total": 1, "files": {"x": 1}}}
lw = lintmsg.lowered(n, b)
check(lw == {"a": {"total": 1, "files": {"y": 1}}, "b": b["b"]}, f"lowered(): only down, nothing added: {lw}")

# ---- 4. check_rules
d = tree({"kalmido/core/env.py": "import os\nV = os.environ.get('X')\n", "kalmido/m.py": "x = 1  # the rule\n",
          "mcp/agent_job.py": "def write_json(p, d):\n    pass\n", "mcp/agent_run.py": "def run():\n    pass\n",
          "static/js/z.js": "api('POST', '/api/x', {});\n"})
try:
    baseline_of(d, "check_rules", "rules_baseline.json")
    rc, out = run(RUL, d, "-v")
    check(rc == 0 and "env 0" in out and "client-write 1" in out, f"core/env.py itself is no finding; the start is green ({out[-300:]})")
    put(d, "kalmido/m.py", "import os\nx = int(os.environ.get('N', '3'))  # 2.1403.0 (#7143): the rule\n")
    rc, out = run(RUL, d)
    check(rc == 1 and "rule env: 1, the baseline allows 0" in out and "env_int / env_bool" in out,
          f"os.environ outside core/env.py: red with the helper named ({out[-500:]})")
    check("notice (not red yet): rule version-mark: 1" in out,
          f"a version mark: the total is a notice, red is an added line (pr_lint marks) ({out[-500:]})")
    check(NOT in out, "check_rules says not to suppress it")
    rc, out = run(RUL, d, "--notice")
    check(rc == 0 and "notice (not red yet): rule env: 1" in out, f"--notice: env is a notice, pr_lint holds it per change ({out[-300:]})")
    put(d, "kalmido/m.py", "x = 1  # the rule\n")
    put(d, "mcp/agent_run.py", "def run():\n    pass\n\n\ndef write_json(p, d):\n    pass\n")
    rc, out = run(RUL, d)
    check(rc == 1 and "rule mcp-dup: 2" in out and "shared starter module" in out, f"a starter helper defined twice: red ({out[-400:]})")
    put(d, "mcp/agent_run.py", "def run():\n    pass\n")
    put(d, "static/js/z.js", "api('POST', '/api/x', {});\napi('DELETE', '/api/x/1');\n")
    rc, out = run(RUL, d)
    check(rc == 0 and "notice (not red yet): rule client-write: 2" in out, f"a further write in the client: a notice ({out[-300:]})")
    # #7262: the product rules seen in the code text (docs/dev/produkt-regeln.md)
    os.makedirs(os.path.join(d, "static", "i18n"), exist_ok=True)
    put(d, "static/js/miniwin.js", "function mw_open(id) { return window.open('/?mini=1'); }\n")
    put(d, "static/i18n/de.json", '{"Like it 👍": "Gefällt 👍", "Save": "Speichern"}\n')
    rc, out = run(RUL, d)
    check(rc == 0 and "window-open" not in out and "rule emoji" not in out,
          f"#7262: window.open inside miniwin.js and the thumbs in a text are no finding ({out[-300:]})")
    put(d, "static/js/y.js", "function show(u) { window.open(u, '_blank'); }\n")
    rc, out = run(RUL, d)
    check(rc == 1 and "rule window-open: 1, the baseline allows 0" in out and "mw_desk()" in out,
          f"#7262: a new window.open in the client: red, the way behind mw_desk() named ({out[-400:]})")
    os.remove(os.path.join(d, "static/js/y.js"))
    put(d, "static/i18n/de.json", '{"Show as chip": "Als Chip zeigen", "Done 🎉": "Fertig 🎉", "Files": "Meine Ablage"}\n')
    rc, out = run(RUL, d)
    check(rc == 1 and "rule wording: 2, the baseline allows 0" in out and "rule emoji: 1, the baseline allows 0" in out
          and "Privat" in out, f"#7262: 'chip', an old name of Private and an emoji in the texts: red ({out[-500:]})")
finally:
    shutil.rmtree(d, ignore_errors=True)

# ---- 5. red_hint: hint on red, nothing on green
for code, want in (("sys.exit(1)", True), ("sys.exit(0)", False), ("pass", False)):
    r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {os.path.join(ROOT, 'tools')!r}); import lintmsg\n"
                        f"with lintmsg.red_hint('t', 'because', 'that'):\n    print('finding')\n    {code}"],
                       capture_output=True, text=True, timeout=60)
    has = "t: Why: because" in r.stdout and "t: Instead: that" in r.stdout and NOT in r.stdout
    check(has == want and r.stdout.index("finding") == 0, f"red_hint on {code}: hint {has}, want {want} ({r.stdout!r})")

# ---- 6. every check says why and what instead; CI runs the new checks; the repo matches its baselines
tools = sorted(f for f in os.listdir(os.path.join(ROOT, "tools")) if re.fullmatch(r"check_\w+\.py", f))
bare = []
for f in tools:
    s = open(os.path.join(ROOT, "tools", f), encoding="utf-8").read()
    if not ("lintmsg" in s and ("LINT_WHY" in s or "WHY = " in s or "RULES = {" in s)):
        bare.append(f)
check(len(tools) >= 35 and not bare, f"every tools/check_*.py prints Why / Instead through lintmsg: missing {bare}")
ci = open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8").read()
check("run: python tools/check_suppress.py -v --notice" in ci and "run: python tools/check_rules.py -v --notice" in ci,
      "ci.yml runs check_suppress and check_rules in the lint job (the Mac lint and the train take the steps from there)")
sem = open(os.path.join(ROOT, ".semgrep", "sql_ident.yml"), encoding="utf-8").read()
check("Why:" in sem and "Instead:" in sem and NOT in sem, "the own semgrep rule's message says why, what instead and not to suppress")
rc, out = run(SUP, ROOT, "--notice")
check(rc == 0, f"check_suppress --notice on the repo: green (a drift of main is a notice): {out[-600:]}")
rc, out = run(RUL, ROOT, "--notice")
check(rc == 0, f"check_rules --notice on the repo: green: {out[-600:]}")

print(f"p21403_c_suppress: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
