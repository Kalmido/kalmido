#!/usr/bin/env python3
# kalmido-suite: after=freelancer_coverage nodata
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
# 2.1386.0 (#6668, review F1): the long-lived token of a team agent per request reaches the classes REQ_MAIN_PASS plus the
# routes of REQ_MAIN_CHANNEL by name -- never a class mine / send / pin as a whole (run_person() is None for that token, so
# nothing caps them: /search, /news, /time/*, /office/*, /briefing ... reached every project and person of the agent).
def _lit(name):
    for n in tree.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == name:
            v = n.value
            if isinstance(v, ast.Call) and getattr(v.func, "id", "") == "frozenset":
                v = v.args[0]
            return ast.literal_eval(v)
    return None


mpass, chan = _lit("REQ_MAIN_PASS"), set(_lit("REQ_MAIN_CHANNEL") or ())
check(set(mpass or ()) == {"own", "safe", "noagent"}, f"F1: REQ_MAIN_PASS is own / safe / noagent only {mpass}")
check(chan and chan <= set(table), f"F1: REQ_MAIN_CHANNEL names routes of RUN_ROUTES {sorted(chan - set(table))}")
opened = sorted(k for k, (cls, _) in table.items() if cls.partition(":")[0] in (mpass or ()) or k in chan)
for k in opened:
    kind = table[k][0].partition(":")[0]
    check(kind in ("own", "safe", "noagent") or k.split(" ", 1)[1].startswith("/agent/"),
          f"F1: {k} ({table[k][0]}) is open to the long-lived token only as its own data or its /agent channel")
for k in ("GET /search", "GET /news", "GET /time/entries", "PATCH /time/entries/{}", "GET /time/gaps", "GET /office/docs",
          "POST /office/invoices", "GET /briefing", "GET /me/waiting", "GET /layouts/blocks", "GET /chat-attachments/{}",
          "POST /agent/proposals", "GET /agent/rules"):
    check(k in table and k not in opened, f"F1: {k} needs the request token (closed to the long-lived token)")
print(f"p6454_c_run_routes: {len(table)} routes; {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
