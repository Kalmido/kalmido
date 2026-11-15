#!/usr/bin/env python3
# kalmido-suite: nodata
"""#6201: tests/stages.py --touched takes for a changed stylesheet the suites that name the classes, ids and data-act values of its
CHANGED rules, and for a changed rule inside a phone media query (max-width up to 767px) the phone suites of the client modules that
render those names. #3835 hid row symbols on phones in one stylesheet; eleven phone suites that never name the file were red for
several trains. Static, no container. Invented names in the small tree.
 - css_phone_media: max-width 767px / 30rem is a phone query, 768px, min-width and pointer only are not
 - css_rules: selectors, lines and the phone flag, comments and @import lines skipped, nested @-blocks
 - css_changed_rules: only the rules a diff touches, the removed ones from the old side, a changed @media line takes its rules
 - a changed rule picks the suite naming its class; an unchanged rule of the same file does not; a phone rule adds the phone suite of
   the module rendering the class, a desktop suite of that module does not come along that way
 - the #3835 stylesheet (the real one, as new): p251_ui, p2458_b_ui and p2190_family_ui among the suites of --touched, not too many"""
import os
import shutil
import subprocess
import sys
import tempfile

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
sys.path.insert(0, os.path.join(N, "..", "tools"))
from kt import FAILS, OKS, check  # noqa: E402
import stages  # noqa: E402

ROOT = os.path.dirname(N)

for q, want in (("(max-width:767px)", True), ("(max-width: 599px)", True), ("(max-width:30rem)", True),
                ("(pointer:coarse),(max-width:767px)", True), ("(min-width:600px) and (max-width:767px)", True),
                ("(max-width:768px)", False), ("(min-width:768px)", False), ("(pointer:coarse)", False), ("(max-width:899px)", False)):
    check(stages.css_phone_media("@media " + q) is want, f"phone query {q}: {want}")

CSS = """/* .zzcomment{x} is a comment */
@import url(x.css);
.qqalpha .qqbeta{color:red}
@media (max-width:767px){
  .qqgamma{display:none}
  @supports (display:grid){ #qqdelta{display:grid} }
}
.qqeps[data-act="qq-act"]{margin:0}
"""
rules = stages.css_rules(CSS)
sel = {r[0]: r for r in rules}
check(set(sel) == {".qqalpha .qqbeta", ".qqgamma", "#qqdelta", '.qqeps[data-act="qq-act"]'}, f"the rules: {sorted(sel)}")
check(sel[".qqalpha .qqbeta"][1:4] == (3, 3, False), f"a plain rule: line 3, no phone: {sel['.qqalpha .qqbeta']}")
check(sel[".qqgamma"][3] and sel["#qqdelta"][3], "rules inside the phone query (also nested) are phone rules")
check(sel[".qqgamma"][4] == (4,), f"the enclosing @media line: {sel['.qqgamma']}")
check(stages.css_tokens('.qqeps[data-act="qq-act"] > .iconbtn #qqid') == {"qqeps", "qq-act", "iconbtn", "qqid"}, "the names of a selector")
check(stages.css_tokens(".sr .ab") == set(), "names shorter than 4 characters are no names")


def git(root, *a):
    subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@example.com", *a], check=True, capture_output=True)


with tempfile.TemporaryDirectory() as tmp:
    for d in ("tests", "static/css", "static/js"):
        os.makedirs(os.path.join(tmp, d))
    names = ["api", "named_ui", "same_ui", "phone_ui", "desk_ui", "other_ui"]
    open(os.path.join(tmp, "tests", "suites.txt"), "w").write(
        "\n".join(("fresh; " if i == 0 else "       ") + f"run {n} node {n}.js" for i, n in enumerate(names)) + "\n")
    body = {"named_ui": "'.qqbeta'\n", "same_ui": "'.qqeps'\n", "phone_ui": "viewport: {width: 390, height: 844}\nqqRowDraw()\n",
            "desk_ui": "viewport: {width: 1280, height: 800}\nqqRowDraw()\n", "other_ui": "viewport: {width: 390}\n"}
    for n in names:
        open(os.path.join(tmp, "tests", n + ".js"), "w").write(body.get(n, "x\n"))
    open(os.path.join(tmp, "tests", "skip.txt"), "w").write("#\n")
    open(os.path.join(tmp, "tests", "run_all.sh"), "w").write('eval "$LIST"\n')
    shutil.copy(os.path.join(N, "suites.py"), os.path.join(tmp, "tests", "suites.py"))
    open(os.path.join(tmp, "static", "js", "qqmod.js"), "w").write("function qqRowDraw() {\n  return '<div class=\"qqgamma\">';\n}\n")
    css = os.path.join(tmp, "static", "css", "qq.css")
    open(css, "w").write(CSS)
    git(tmp, "init", "-q")
    git(tmp, "add", ".")
    git(tmp, "commit", "-qm", "base")
    r = stages.Repo(tmp, os.path.join(tmp, "tests", "run_all.sh"))
    open(css, "w").write(CSS.replace("color:red", "color:blue"))
    ch = stages.css_changed_rules("HEAD", None, "static/css/qq.css", tmp)
    check(ch == [(".qqalpha .qqbeta", False)] * 2, f"a changed declaration: its rule, old and new side: {ch}")
    h = stages.css_rule_hits(r, "static/css/qq.css", "HEAD", None)
    check("named_ui" in h and "(#6201)" in h["named_ui"], f"the suite naming the changed rule's class: {h}")
    check("same_ui" not in h and "phone_ui" not in h, f"an unchanged rule of the same file picks nothing: {h}")
    open(css, "w").write(CSS.replace("display:none", "display:block"))
    h = stages.css_rule_hits(r, "static/css/qq.css", "HEAD", None)
    check("phone_ui" in h and "qqmod.js" in h["phone_ui"], f"a phone rule: the phone suite of the module that renders the class: {h}")
    check("desk_ui" not in h and "other_ui" not in h and "named_ui" not in h, f"no desktop suite, no unrelated phone suite: {h}")
    open(css, "w").write(CSS.replace("@media (max-width:767px)", "@media (max-width:599px)"))
    ch = stages.css_changed_rules("HEAD", None, "static/css/qq.css", tmp)
    check({s for s, _ in ch} == {".qqgamma", "#qqdelta"}, f"a changed @media line takes the rules inside it: {ch}")
    open(css, "w").write(CSS.replace(".qqeps", ".qqzeta"))
    ch = stages.css_changed_rules("HEAD", None, "static/css/qq.css", tmp)
    check({s for s, _ in ch} == {'.qqeps[data-act="qq-act"]', '.qqzeta[data-act="qq-act"]'}, f"a renamed rule: old and new: {ch}")
    h = stages.css_rule_hits(r, "static/css/qq.css", "HEAD", None)
    check("same_ui" in h, f"the suite naming the removed class: {h}")
    check(stages.css_rule_hits(r, "static/css/qq.css", None, None) == {}, "without a base (a file list): no rule hits")
    git(tmp, "add", ".")
    git(tmp, "commit", "-qm", "change")
    order, why, unm = stages.touched(r, ["static/css/qq.css"], "HEAD^", "HEAD")
    check("same_ui" in order and "(#6201)" in why["same_ui"], f"--touched takes them: {order}")

# the #3835 stylesheet (the real file, as a new file): the phone suites that were red then come along. The diff is made in a small
# tree (the CI checkout has no history), the suites are this repo's
PHROWS = "static/css/start-phrows-" + "3835.css"
if os.path.exists(os.path.join(ROOT, PHROWS)):
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "static", "css"))
        open(os.path.join(tmp, "x"), "w").write("x\n")
        git(tmp, "init", "-q")
        git(tmp, "add", ".")
        git(tmp, "commit", "-qm", "base")
        shutil.copy(os.path.join(ROOT, PHROWS), os.path.join(tmp, PHROWS))
        git(tmp, "add", ".")
        git(tmp, "commit", "-qm", "new stylesheet")
        rules = stages.css_changed_rules("HEAD^", "HEAD", PHROWS, tmp)
    check(rules and any(ph for _, ph in rules), f"#3835: its rules, phone rules among them: {len(rules or [])}")
    repo = stages.Repo(ROOT, os.path.join(N, "run_all.sh"))
    real = stages.css_changed_rules
    stages.css_changed_rules = lambda *a: rules
    try:
        order, why, unm = stages.touched(repo, [PHROWS], "BASE", "HEAD")
    finally:
        stages.css_changed_rules = real
    skip = repo.skipped()
    for s in ("p251_ui", "p2458_b_ui", "p2190_family_ui"):
        if s in repo.group_of and s not in skip:
            check(s in order, f"#3835: {s} runs: {why.get(s)}")
    check(unm == [], f"#3835: not unmapped: {unm}")
    check(len(order) <= 70, f"#3835: not the whole run, under the Mac runner's 80: {len(order)}")

print(f"p6201_cssrules: {OKS[0]} ok, {len(FAILS)} failed")
