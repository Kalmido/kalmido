#!/usr/bin/env python3
# kalmido-suite: nodata
"""#6977 F1 (Fable reading of job/5201) and #6605: the organisation roles the app checks are narrowed in one place. Static, no
container.
 - user_orgs, org_role and org_roles_of (accounts/orgs.py, accounts/orgroles.py) all go through org_roles_cap: a personal
   agent has at most its person's role (#6605), a support session only the organisations with their own grant (#6977 F1)
 - the stored memberships without the cap (org_roles_read, user_orgs(raw=True)) are read only by those functions and by the
   account's own access context (core/access.py _orgs_of; _ctx_support narrows a support session there itself)
 - no reading route (GET) works out the person's organisations itself from org_members and then reads in the system context:
   a role check of its own there would skip the narrowing (a support session would read past it)
usage: python3 -I tests/p6977_support_roles_src_test.py"""
import ast
import os
import re
import sys

from kt import FAILS, OKS, check

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def tree(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return ast.parse(f.read())


def func(t, name):
    return next((n for n in ast.walk(t) if isinstance(n, ast.FunctionDef) and n.name == name), None)


def calls(fn):
    return {n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "") for n in ast.walk(fn) if isinstance(n, ast.Call)}


ORGS, ROLES = tree("kalmido/accounts/orgs.py"), tree("kalmido/accounts/orgroles.py")
for t, name in ((ORGS, "user_orgs"), (ORGS, "org_role"), (ROLES, "org_roles_of")):
    fn = func(t, name)
    check(fn is not None and "org_roles_cap" in calls(fn), f"{name} goes through org_roles_cap")
cap = func(ROLES, "org_roles_cap")
src = ast.unparse(cap) if cap else ""
check("owner_id" in src and "ACX_SUPPORT_ORGS" in src, "org_roles_cap: the agent's person (#6605) and the support narrowing (#6977 F1)")

# who reads the memberships without the cap
ALLOWED_RAW = {("kalmido/accounts/orgroles.py", "org_roles_of"), ("kalmido/accounts/orgs.py", "user_orgs"),
               ("kalmido/accounts/orgs.py", "org_role"), ("kalmido/core/access.py", "_orgs_of")}
raw, gets = set(), []
for dp, _, fs in os.walk(os.path.join(ROOT, "kalmido")):
    for fname in fs:
        if not fname.endswith(".py"):
            continue
        path = os.path.join(dp, fname)
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        if "/migrations" in rel:
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if "org_roles_read" not in text and "raw=True" not in text and "@app." not in text:
            continue
        for fn in ast.walk(ast.parse(text)):
            if not isinstance(fn, ast.FunctionDef):
                continue
            body = ast.unparse(fn)
            for n in ast.walk(fn):
                if isinstance(n, ast.Call):
                    nm = n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
                    if nm == "org_roles_read" or (nm == "user_orgs" and any(k.arg == "raw" for k in n.keywords)):
                        raw.add((rel, fn.name))
            deco = [ast.unparse(d) for d in fn.decorator_list]
            get = any(d.startswith("app.get(") or (d.startswith("app.route(") and ("GET" in d or "methods" not in d)) for d in deco)
            if get and "system_ctx(" in body and re.search(r"org_members[^\"']*user_id\s*=", body):
                gets.append(f"{rel}:{fn.lineno} {fn.name}")
check(raw and raw <= ALLOWED_RAW, f"the uncapped memberships only where allowed: {sorted(raw - ALLOWED_RAW)}")
check(not gets, f"no reading route checks membership itself and then reads as system: {gets}")

print(f"p6977_support_roles_src: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
