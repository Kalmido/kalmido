#!/usr/bin/env python3
"""2.1287.0 (#6454, review P2): every route of /api/v1 is named in kalmido/api/runfor.py RUN_ROUTES -- how it is held in a
team agent's run for a person (cut, cap, mine, pin:<parameter>, send, org, closed, own, noagent, safe). A new route fails
here until somebody decides; until then run_gate closes it in such a run. No container needed: reads kalmido/.
usage: python3 tests/p6454_c_run_routes_test.py"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from routes_ast import app_routes  # noqa: E402
from kt import FAILS, OKS, check  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
src = open(os.path.join(ROOT, "kalmido", "api", "runfor.py"), encoding="utf-8").read()
tree = ast.parse(src)
table = None
for n in tree.body:
    if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "RUN_ROUTES":
        table = ast.literal_eval(n.value)
pas = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "RUN_PASS")
classes = set(pas) | {"pin", "org", "closed"}
check(isinstance(table, dict) and table, "RUN_ROUTES is a literal dict")
found, problems = app_routes(ROOT)
for p in problems:
    check(False, f"route the guard cannot check: {p}")
v1 = {r.split(" ", 1)[0] + " " + r.split(" ", 1)[1][len("/api/v1"):] for r in found if " /api/v1/" in r}
missing = sorted(v1 - set(table))
stale = sorted(set(table) - v1)
check(not missing, f"every /api/v1 route is named in RUN_ROUTES (missing: {missing[:20]})")
check(not stale, f"RUN_ROUTES names no route that is gone (stale: {stale[:20]})")
for k, (cls, why) in table.items():
    kind, _, par = cls.partition(":")
    check(kind in classes, f"{k}: known class {cls}")
    check(kind != "pin" or par, f"{k}: pin names its parameter")
    check(bool(str(why).strip()), f"{k}: says by what it is held")
# the agent's own channel and the routes of the review findings stay held as decided
for k, want in (("GET /agent/chats", "mine"), ("GET /agent/events", "mine"), ("GET /agent/jobs", "mine"), ("GET /briefing", "pin:user_id"),
                ("GET /me/waiting", "pin:user_id"), ("GET /office/docs", "pin:requested_by"), ("GET /folders", "closed")):
    check(table.get(k, ("?",))[0] == want, f"{k} is {want}")
print(f"p6454_c_run_routes: {len(table)} routes; {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
