#!/usr/bin/env python3
# kalmido-suite: nodata
"""#7294: the building-block duty of the one grip as a check - tools/griff_lint.py (the rules) and tools/pr_lint.py "griff"
(only what a change adds, the rules from the BASE commit). No container, standard library only.
Rules: a new 17.5rem side column beside 1fr is red, with the grip's variable or /* griff-ok: REASON */ green, griff-ok without
a reason red; auto-fill tiles green; a column from var(--w-leiste) (no fallback) red, a label column var(--dc-lw,7.5rem)
green; flex: 0 0 var(--x) red, flex: 0 1 14rem (a field that shrinks) green; #pop.neu{width:20rem} red, a menu with griff-ok
green; a rule only inside the phone @media green; a dialog card green. pr_lint: the stock and an unchanged red declaration
in an edited rule pass, a rule moved unchanged into another file passes, a new one is red with why / instead."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
LINT = os.path.join(TOOLS, "pr_lint.py")
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
from kt import FAILS, OKS, check  # noqa: E402
import griff_lint as gl  # noqa: E402


def red(css):
    return [w for _l, _s, _d, w in gl.findings(css)]


def sh(repo, *a, env=None):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, check=True, env=env).stdout.strip()


def commit(repo, files, subject):
    for path, text in files.items():
        full = os.path.join(repo, path)
        if text is None:
            os.remove(full)
            continue
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)
    sh(repo, "add", "-A")
    env = dict(os.environ, GIT_AUTHOR_NAME="Kalmido", GIT_AUTHOR_EMAIL="noreply@kalmido.com", GIT_COMMITTER_NAME="Kalmido",
               GIT_COMMITTER_EMAIL="noreply@kalmido.com")
    sh(repo, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", subject, env=env)
    return sh(repo, "rev-parse", "HEAD")


def lint(repo, base):
    e = {k: v for k, v in os.environ.items() if not k.startswith("KALMIDO_PRIVACY") and k not in ("KALMIDO_ALLOWED_EMAILS", "GITHUB_ACTIONS")}
    p = subprocess.run([sys.executable, LINT, "--repo", repo, "--base", base, "--only", "griff"], capture_output=True, text=True, env=e)
    return p.returncode, p.stdout + p.stderr


def main():
    # ---- the rules
    check(red(".shv{display:grid;grid-template-columns:minmax(0,1fr) 17.5rem}"), "a new 17.5rem side column beside 1fr is red")
    check(not red(".shv{grid-template-columns:minmax(0,1fr) var(--g-shv-side,17.5rem)}"), "with the grip's variable: green")
    check(not red(".shv{grid-template-columns:minmax(0,1fr) 17.5rem}  /* griff-ok: the preview has its own zoom */"), "griff-ok trailing the rule: green")
    check(not red("/* griff-ok: a fixed legend */\n.shv{grid-template-columns:minmax(0,1fr) 17.5rem}"), "griff-ok on the line before: green")
    check(red("/* griff-ok: */\n.shv{grid-template-columns:minmax(0,1fr) 17.5rem}"), "griff-ok without a reason: still red")
    check(red(".a{x:1}  /* griff-ok: only for .a */\n.shv{grid-template-columns:minmax(0,1fr) 17.5rem}"), "griff-ok of the rule before does not cover the next")
    check(not red(".tiles{grid-template-columns:repeat(auto-fill,minmax(14rem,1fr))}"), "auto-fill tiles: green")
    check(not red(".g{grid-template-columns:1fr 2fr}"), "a pure fr grid: green")
    check(red(".lst{grid-template-columns:minmax(var(--w-leiste-min),var(--w-leiste)) minmax(0,1fr)}"), "a column from a variable without a fallback: red")
    check(not red(".f{grid-template-columns:var(--dc-lw,7.5rem) 1fr}"), "a label column 7.5rem (fallback): green")
    check(not red(".row{grid-template-columns:2rem minmax(0,1fr) 6rem}"), "icon and number columns below 12rem: green")
    check(red(".tl-name{flex:0 0 var(--tl-name)}"), "flex: 0 0 var(--x): red")
    check(not red(".q{flex:0 1 14rem}"), "a field that may shrink (flex: 0 1 14rem): green")
    check(red("#pop.neu{width:20rem}"), "a new pop-up with a fixed width: red")
    check(red(".float{position:fixed;width:min(24rem,calc(100vw - 2rem))}"), "position fixed with a width in min(): red")
    check(not red("#pop.menu{width:20rem}  /* griff-ok: a menu sized to its entries */"), "a menu with griff-ok: green")
    check(not red(".float::before{position:absolute;width:35rem}"), "a pseudo element (decoration): green")
    check(not red("@media (max-width:767px){ .shv{grid-template-columns:minmax(0,1fr) 17.5rem} }"), "only inside the phone @media: green")
    check(red("@media (min-width:768px){ .shv{grid-template-columns:minmax(0,1fr) 17.5rem} }"), "inside a computer @media: red")
    check(not red(".modal.big .card{width:40rem}"), "a dialog card: green (its grip comes by itself)")
    check(not red(".lsd2{grid-template-columns:var(--g-x,minmax(var(--w-leiste-min),var(--w-leiste))) minmax(0,1fr)}"), "the grip's variable with a stock fallback: green")

    # ---- pr_lint: only what a change adds, from the base
    with tempfile.TemporaryDirectory() as repo:
        sh(repo, "init", "-q", "-b", "main")
        tl = {f"tools/{n}.py": open(os.path.join(TOOLS, f"{n}.py"), encoding="utf-8").read() for n in ("griff_lint", "lintmsg")}
        b0 = commit(repo, {"README.md": "x\n", "static/app.css": ".old{grid-template-columns:minmax(0,1fr) 20rem}\n"}, "start #1")
        commit(repo, {"static/app.css": ".old{grid-template-columns:minmax(0,1fr) 20rem}\n.new{grid-template-columns:minmax(0,1fr) 17.5rem}\n"}, "#7294: x")
        rc, out = lint(repo, b0)
        check(rc == 0 and "not in the base" in out, f"a base without tools/griff_lint.py: a notice, not red {rc} {out[-400:]}")
        b1 = commit(repo, {**tl, "static/app.css": ".old{grid-template-columns:minmax(0,1fr) 20rem}\n"}, "#7294: the check")
        commit(repo, {"static/app.css": ".old{grid-template-columns:minmax(0,1fr) 20rem;color:red}\n.ok{color:blue}\n"}, "#7294: stock")
        rc, out = lint(repo, b1)
        check(rc == 0 and "pr_lint griff: ok" in out, f"the stock and an unchanged red declaration of an edited rule pass {rc} {out[-400:]}")
        b2 = sh(repo, "rev-parse", "HEAD")
        commit(repo, {"static/app.css": ".ok{color:blue}\n", "static/css/moved.css": ".old{grid-template-columns:minmax(0,1fr) 20rem;color:red}\n"}, "#7294: move")
        rc, out = lint(repo, b2)
        check(rc == 0 and "pr_lint griff: ok" in out, f"a rule moved unchanged into another file passes {rc} {out[-400:]}")
        b3 = sh(repo, "rev-parse", "HEAD")
        commit(repo, {"static/css/side.css": ".side{display:grid;\n  grid-template-columns:minmax(0,1fr) 17.5rem;\n  gap:1rem}\n"}, "#7294: new")
        rc, out = lint(repo, b3)
        check(rc == 1 and "static/css/side.css:2" in out and "griff-ok" in out and "grip_col" in out, f"a new fixed side column is red with where / why / instead {rc} {out[-600:]}")
        commit(repo, {"static/css/side.css": ".side{display:grid;\n  grid-template-columns:minmax(0,1fr) var(--g-side,17.5rem);\n  gap:1rem}\n"}, "#7294: with the grip")
        rc, out = lint(repo, b3)
        check(rc == 0, f"... with the grip's variable it passes {rc} {out[-400:]}")
    print(f"p7294_griff_lint: {OKS[0]} ok, {len(FAILS)} failed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
