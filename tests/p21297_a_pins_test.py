#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.1297.0 (#6509): the rest of the supply chain pinned (tools/pins.py, offline, Python standard library only).
 - the repository itself is clean: no problem in tools/pins.py's offline check
 - workflows: a pip install with a package==version, without --require-hashes or from a lock outside CI_LOCKS is red;
   --require-hashes -r <known lock> is fine; an image by tag only is red, by tag@sha256 fine, an image of WF_UNPINNED
   passes until it has a digest (then the entry is stale and red), an entry no workflow names is red
 - CI locks: a lock without hashes is red, a pin of the source file missing in the lock (or another version) is red
 - vendor files: a changed byte in a bundled file turns its README's sha256 line red, a missing file too
 - --osv sees the packages of tools/codemirror/package-lock.json (CodeMirror bundle)
usage: python3 tests/p21297_a_pins_test.py"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pins  # noqa: E402
from kt import check, done  # noqa: E402

out = pins.problems()
check(out == [], f"#6509: the repository passes the offline pin check: {out}")

# ---- workflows
SHA = "sha256:" + "a" * 64
ok = [("w.yml", "steps:\n  - run: pip install --require-hashes -r tools/ci/lint.lock\n"
                "  - run: docker run --rm aquasec/trivy:0.76.2@" + SHA + " image x\n"
                "  - uses: actions/checkout@abc # v7\n  # pip install foo==1 in a comment\n")]
check(pins.workflow_problems(ok, {}) == [], f"#6509: a hash lock and an image by digest pass: {pins.workflow_problems(ok, {})}")
for line, why in (("pip install ruff==0.17.4", "a package by version only"),
                  ("pip install -r tests/requirements.txt", "a requirements file without hashes"),
                  ("pip install --require-hashes -r tools/other.lock", "a lock outside CI_LOCKS"),
                  ("pip install --require-hashes -r tools/ci/lint.lock extra==1", "a package beside the lock")):
    p = pins.workflow_problems([("w.yml", f"  - run: {line}\n")], {})
    check(len(p) == 1, f"#6509: {why} is red: {p}")
sg = "pip install --require-hashes -r tools/ci/semgrep.lock && python3 tools/pins.py --installed semgrep=={}"
ver = pins.pins_of(open(os.path.join(ROOT, "tools/ci/semgrep.lock"), encoding="utf-8").read())["semgrep"]
check(pins.workflow_problems([("w.yml", f"  - run: {sg.format(ver)}\n")], {}) == [], "#6509: the semgrep line with the lock's version passes")
p = pins.workflow_problems([("w.yml", f"  - run: {sg.format('0.0.1')}\n")], {})
check(len(p) == 1 and "--installed" in p[0], f"#6509: --installed with another version than the lock is red: {p}")
check(pins.installed_problems(["x==1.0", "y==2"], {"x": "1.0", "y": "3"}.get) == ["y: installed 3, the workflow names 2"],
      "#6509: --installed compares with the installed versions")
img = [("w.yml", "        run: |\n          docker run --rm ghcr.io/zaproxy/zaproxy:2.17.0 \\\n            zap-baseline.py\n")]
check(len(pins.workflow_problems(img, {})) == 1, "#6509: an image by tag only is red")
check(pins.workflow_problems(img, {"ghcr.io/zaproxy/zaproxy": "task"}) == [], "#6509: an image of WF_UNPINNED passes")
pinned = [("w.yml", f"          docker run ghcr.io/zaproxy/zaproxy:2.17.0@{SHA} zap\n")]
check(len(pins.workflow_problems(pinned, {"ghcr.io/zaproxy/zaproxy": "task"})) == 1, "#6509: a pinned image still in WF_UNPINNED is red")
check(len(pins.workflow_problems(ok, {"ghcr.io/x/y": "task"})) == 1, "#6509: a WF_UNPINNED entry no workflow names is red")
check(all(r in [t[1] for _, x in pins.workflow_texts() for t in pins.workflow_images(x)] for r in pins.WF_UNPINNED),
      "#6509: every WF_UNPINNED entry is still in a workflow")

# ---- CI locks against their source (in a copy of the files the check reads)
tmp = tempfile.mkdtemp(prefix="p21297a-")
try:
    for rel in list(pins.CI_LOCKS) + list(pins.CI_LOCKS.values()):
        os.makedirs(os.path.join(tmp, os.path.dirname(rel)), exist_ok=True)
        shutil.copy(os.path.join(ROOT, rel), os.path.join(tmp, rel))
    real = pins.ROOT
    pins.ROOT = tmp
    try:
        check(pins.ci_lock_problems() == [], f"#6509: the copied locks pass: {pins.ci_lock_problems()}")
        with open(os.path.join(tmp, "tools/ci/lint.in"), "a", encoding="utf-8") as f:
            f.write("ruff==0.0.1\n")
        p = pins.ci_lock_problems()
        check(any("tools/ci/lint.lock" in x and "ruff" in x for x in p), f"#6509: a pin of the source file the lock does not hold is red: {p}")
        with open(os.path.join(tmp, "tools/ci/tzdata.lock"), "w", encoding="utf-8") as f:
            f.write("tzdata==2025.2\n")
        p = pins.ci_lock_problems()
        check(any("tzdata" in x and "no hash" in x for x in p), f"#6509: a lock line without hash is red: {p}")
        os.remove(os.path.join(tmp, "tests/requirements.lock"))
        check(any("tests/requirements.lock: missing" in x for x in pins.ci_lock_problems()), "#6509: a missing lock is red")
    finally:
        pins.ROOT = real
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---- vendor files against the sha256 lines of their README
tmp = tempfile.mkdtemp(prefix="p21297a-")
try:
    shutil.copytree(os.path.join(ROOT, "static/vendor/katex"), os.path.join(tmp, "static/vendor/katex"))
    real = pins.ROOT
    pins.ROOT = tmp
    try:
        check(pins.vendor_problems() == [], f"#6509: an unchanged vendor folder passes: {pins.vendor_problems()}")
        with open(os.path.join(tmp, "static/vendor/katex/katex.min.css"), "ab") as f:
            f.write(b"/* changed */")
        p = pins.vendor_problems()
        check(len(p) == 1 and "katex.min.css" in p[0], f"#6509: a changed vendor file is red: {p}")
        os.remove(os.path.join(tmp, "static/vendor/katex/katex.min.js"))
        check(any("katex.min.js" in x and "missing" in x for x in pins.vendor_problems()), "#6509: a missing vendor file is red")
    finally:
        pins.ROOT = real
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---- the CodeMirror bundle's packages go to OSV too
cm = dict(pins.codemirror_targets())
check(len(cm) >= 10 and "@codemirror/state" in cm and all(cm.values()), f"#6509: the CodeMirror lock's packages with versions: {sorted(cm)[:5]}")
asked = []
pins.osv_check(lambda n, v: asked.append(n) or [], None, {})
check("@codemirror/state" in asked and "pdfjs-dist" in asked, f"#6509: --osv asks for the CodeMirror packages too ({len(asked)} asked)")

sys.exit(done("p21297_a_pins_test"))
