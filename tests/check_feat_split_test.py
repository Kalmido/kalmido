#!/usr/bin/env python3
# kalmido-suite: after=p2501_a_nosham nodata
"""2.1327.0 (#6823): tools/check_feat_split.py and the one reading of the module switches (kalmido/core/access.py
feat_list / feat_in / feats / feat_has). Static, no container.
 - a split of s.get("features") / s["features"] / usettings(...)["features"] outside core/access.py is red (also over two
   lines, also rsplit); the instance default (USER_DEFAULTS["features"], gsetting "default_features"), another key
   ("features_before"), a comment or a docstring stay quiet; the allowed files (home, migration) stay quiet
 - a file that does not parse is red; the script exits 1 on a finding
 - the repository: no finding
 - feat_has / feat_in / feat_list / feats lifted from core/access.py with a stub database: on, off, empty value (all
   off), no row (the default of USER_DEFAULTS), blanks and doubles in the value, the agent's data lock (DL_FEAT_AREA: off
   for a locked agent, a module outside the lock stays on, a person without a lock and without an organisation as before)
usage: check_feat_split_test.py"""
import ast
import os
import shutil
import sys
import tempfile

from kt import FAILS, OKS, check

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import check_feat_split as fs  # noqa: E402

# ---------------------------------------------------------------- the lint
RED = {
    "get": 'def f(c, uid):\n    return "x" in (usettings(c, uid).get("features") or "").split(",")\n',
    "subscript": 'def f(s):\n    return [x for x in s["features"].split(",") if x]\n',
    "two lines": 'def f(S, u):\n    return "x" in (S[u].get(\n        "features") or "").split(\n        ",")\n',
    "rsplit": 'def f(s):\n    return s.get("features", "").rsplit(",")\n',
}
for what, src in RED.items():
    check(fs.hits_text(src), f"red: {what} {fs.hits_text(src)}")
QUIET = {
    "instance default": 'def f(c):\n    a = USER_DEFAULTS["features"].split(",")\n    return (gsetting(c, "default_features") or "").split(",") + a\n',
    "another key": 'def f(r):\n    return (r.get("features_before") or "").split(",") + r["features_rev"].split(",")\n',
    "comment, docstring": 'def f(s):\n    """s.get("features").split(",") is gone"""\n    # s["features"].split(",")\n    return feat_list(s)\n',
    "no split": 'def f(s):\n    return s.get("features") or ""\n',
}
for what, src in QUIET.items():
    check(fs.hits_text(src) == [], f"quiet: {what} {fs.hits_text(src)}")
check(fs.hits_text("def f(:\n") is None, "a file that does not parse: None")

tmp = tempfile.mkdtemp(prefix="featsplit-")
for rel, text in {"kalmido/core/access.py": RED["get"], "kalmido/core/db.py": RED["subscript"],
                  "kalmido/area/mod.py": "x = 1\n" + RED["get"], "kalmido/area/bad.py": "def f(:\n"}.items():
    os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
    with open(os.path.join(tmp, rel), "w", encoding="utf-8") as f:
        f.write(text)
out = fs.findings(tmp)
check(len(out) == 2 and out[0].startswith("kalmido/area/bad.py: does not parse") and out[1].startswith("kalmido/area/mod.py:3:")
      and "feat_has" in out[1], f"the tree: a split outside the allowed files and a broken file are red, home + migration quiet {out}")
check(fs.main(["x", "--root", tmp]) == 1, "the script: exit 1 on a finding")
shutil.rmtree(tmp, ignore_errors=True)
check(fs.findings() == [], f"the repository: no split of its own {fs.findings()[:5]}")
check(set(fs.ALLOW) == {"kalmido/core/access.py", "kalmido/core/db.py"}, f"the allow list stays the home and the migration {fs.ALLOW}")

# ---------------------------------------------------------------- feat_has & co. lifted from core/access.py
with open(os.path.join(ROOT, "kalmido", "core", "access.py"), encoding="utf-8") as f:
    tree = ast.parse(f.read())
WANT = ("feat_list", "feat_in", "feats", "feat_has", "_feat_locked")
mod = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in WANT], type_ignores=[])
check(len(mod.body) == len(WANT), f"core/access.py defines {WANT}")

DEFAULT = "cal,collab,events"
ROWS = {1: {"features": "contacts,events,time"},       # a person, every module of the test on
        2: {"features": ""},                            # everything switched off
        3: {},                                          # no row: the instance default
        4: {"features": ",time,, time,contacts"},       # blanks and a blank-padded double
        5: {"features": "contacts,events,time"},        # an agent with calendar + contacts locked
        6: {"features": "contacts,events,time"}}        # an agent without a lock
LOCKED = {5: {"calendar", "contacts"}}


def usettings(c, uid):
    s = {"features": DEFAULT}
    s.update(ROWS[uid])
    return s


ns = {"usettings": usettings, "DL_FEAT_AREA": {"events": "calendar", "contacts": "contacts"},
      "dl_area_locked": lambda c, uid, area: area in LOCKED.get(uid, set())}
exec(compile(mod, "core/access.py", "exec"), ns)  # noqa: S102  the functions of the repository, with the stubs above
feat_has, feat_in, feat_list, feats = ns["feat_has"], ns["feat_in"], ns["feat_list"], ns["feats"]

check(feat_has(None, 1, "time") and feat_has(None, 1, "contacts") and feat_has(None, 1, "events"), "on: the switched-on modules")
check(not feat_has(None, 1, "habits") and not feat_has(None, 1, ""), "off: a module not in the list, never the empty name")
check(not any(feat_has(None, 2, f) for f in ("time", "contacts", "events", "cal", "")) and feats(None, 2) == [],
      "an empty value: everything off (not the default)")
check(feat_has(None, 3, "cal") and feat_has(None, 3, "collab") and not feat_has(None, 3, "time") and feats(None, 3) == DEFAULT.split(","),
      "no row: the instance default")
check(feats(None, 4) == ["time", " time", "contacts"] and feat_has(None, 4, "time") and feat_has(None, 4, "contacts"),
      f"blanks out, stored order kept {feats(None, 4)}")
check(not feat_has(None, 5, "contacts") and not feat_has(None, 5, "events") and feat_has(None, 5, "time"),
      "an agent with the data lock: contacts / calendar off, a module outside the lock stays on")
check(feat_has(None, 6, "contacts") and feat_has(None, 6, "events"), "an agent without a lock: as its switches say")
check(feat_has(None, 1, "events", s={"features": "events"}) and not feat_has(None, 1, "time", s={"features": "events"}),
      "s given: the settings handed in count (no second read)")
check(not feat_has(None, 5, "contacts", s={"features": "contacts"}), "s given: the data lock still counts")
check(feat_in({"features": "a,b"}, "b") and not feat_in({"features": "a,b"}, "c") and not feat_in({}, "a") and not feat_in(None, "a")
      and feat_list(None) == [] and feat_list({"features": None}) == [], "feat_in / feat_list: a dict, an empty one, None")

print(f"check_feat_split: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
