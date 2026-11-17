#!/usr/bin/env python3
"""2.1327.0 (#6823): a person's module switches are read in ONE place, kalmido/core/access.py.

The user setting "features" is a comma list of the modules a person switched on. feat_has(c, uid, f) answers "is f on for
this account" (its switch plus the agent's data lock of DL_FEAT_AREA), feat_in(s, f) / feat_list(s) read a settings dict a
loop holds already, feats(c, uid) lists the switches; need_feat (web, 409), api/common.py v1_feature (API v1, 403) and
life/model.py feat_on build on them. A split of the setting anywhere else would be a reading of its own that can drift (a
module off in one place, on in the other; the data lock forgotten) - so it is red here:
  a call X.split(...) whose X contains  <expr>.get("features" ...)  or  <expr>["features"]
  not: USER_DEFAULTS["features"] / gsetting(c, "default_features") (the instance default, not a person's switch), other keys
  ("features_before", "features_rev" ...), a docstring or a comment.
Allowed (ALLOW, with the reason): the home kalmido/core/access.py and the migration of kalmido/core/db.py (feats8: it
rewrites the stored value itself, before the app runs).

Read: kalmido/**/*.py parsed with ast. A file that does not parse is red (the lint cannot vouch for it).

usage: python3 tools/check_feat_split.py [-v] [--root DIR]      exit 1 on a finding
Standard library only.
"""
import ast
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "features"
ALLOW = {
    "kalmido/core/access.py": "the home: feat_list / feat_in / feats / feat_has",
    "kalmido/core/db.py": "the migration feats8 rewrites the stored switches itself",
}
HELP = "read the switches through feat_has / feat_in / feat_list / feats of kalmido/core/access.py"


def _reads_features(node):
    """Does the expression read the setting "features" of a settings dict (s.get("features") / s["features"])?"""
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get" and n.args \
                and isinstance(n.args[0], ast.Constant) and n.args[0].value == KEY:
            return True
        if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value == KEY \
                and not (isinstance(n.value, ast.Name) and n.value.id == "USER_DEFAULTS"):
            return True
    return False


def hits_text(text):
    """[line numbers] of the splits of the setting in the Python source text; None if it does not parse."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("split", "rsplit") \
                and _reads_features(node.func.value):
            out.add(node.lineno)
    return sorted(out)


def findings(root=ROOT):
    """[messages] of the server code under root: a split outside ALLOW, a file that does not parse."""
    out = []
    for p in sorted(glob.glob(os.path.join(root, "kalmido", "**", "*.py"), recursive=True)):
        rel = os.path.relpath(p, root).replace(os.sep, "/")
        if rel in ALLOW:
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = hits_text(f.read())
        if lines is None:
            out.append(f"{rel}: does not parse")
        for n in lines or ():
            out.append(f"{rel}:{n}: splits the setting \"features\" itself - {HELP}")
    return out


def main(argv):
    root = argv[argv.index("--root") + 1] if "--root" in argv else ROOT
    out = findings(root)
    for m in out:
        print(m)
    if "-v" in argv or out:
        print(f"check_feat_split: {len(out)} finding(s)")
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
