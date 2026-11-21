#!/usr/bin/env python3
# kalmido-suite: nodata
"""#7633: the one list of every way into and out of an account (kalmido/accounts/accessways.py ACCESS_WAYS) is complete - so the
next way (a token, a key, a link, a target outside) is never forgotten in ses_access_end again (13 fixes of #6354 .. #6558 each
wrote one more by hand). Static like tests/export_coverage_test.py: reads kalmido/core/schema.py (+ migrations.d) and
accessways.py, no container.
 1. every table with a key column (token_hash, secret, secret_hash, pw_hash, *_token_hash) is named in ACCESS_WAYS (a row's
    tables, "table" or "table.column") or in ACCESS_NOT with the reason
 1b. #7633 F1: every column with an address outside (OUT: url, *_url, endpoint, webhook, target, smtp_*, redirect_uri, *host,
    *server) is named the same way ("table" or "table.column"), and every target hidden inside sealed data (SEALED, a fixed
    list: a new one is added here and to the list) is a row of ACCESS_WAYS
 2. nothing is stale: every table / column named exists; nothing is in both lists
 3. every row is well-formed: a known end, statements with exactly one "?" (the uid) or a function that exists, "stays" with a
    reason, the security mail of a row (mail) is one of accounts/secmail.py SEC_EVENTS
 3b. F5: every security mail out_new in kalmido/ names its row (sec_mail way=): an "off" row, or a "stays" row with the place
    (where) its closing sentence names - the mail never promises that a new password switches off what stays
 3c. F6: an "off" row switches off also what is already off (after failures): its UPDATE is not limited to what is on
 4. ses_access_end reads the list: no handwritten DELETE / UPDATE of its own any more (sessions.py)
usage: python3 tests/access_ways_test.py"""
import ast
import importlib.util
import os
import re
import sys

N = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(N, "..")
sys.path.insert(0, N)
from kt import FAILS, OKS, check  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tools"))
from check_migrations import schema_src  # noqa: E402

TYPES = "BIGINT|TEXT|INTEGER|DOUBLE|NUMERIC|BOOLEAN|JSONB|BYTEA|REAL|SMALLINT|DATE|TIMESTAMP"
KEYS = ("token_hash", "secret", "secret_hash", "pw_hash")
ACCOUNT = {"users.password_hash"}  # the account's own sign-in: what every row here is measured against
# #7633 F1: a column whose name says "an address outside" (data may go there); _id / _hint / _key / _secret / _at / _by are none
OUT = re.compile(r"(^|_)url$|^urls?_|endpoint|webhook|^target$|^smtp_|redirect_uri|_host$|^host$|server$")
OUT_NO = re.compile(r"_(id|hint|key|secret|at|by|info)$")
# targets outside that live inside sealed data (no column of their own, the pattern cannot see them): each is a row of ACCESS_WAYS
SEALED = {"doc_rules.data": "the webhook action of a document flow (docs/flows.py fl_clean, the address in the sealed flow)"}

schema = re.sub(r"--[^\n]*", "", schema_src(ROOT))
tables = {}
for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\);", schema, re.S):
    tables.setdefault(m.group(1), set()).update(re.findall(rf"(?:^|,|\()\s*\"?(\w+)\"?\s+(?:{TYPES})", m.group(2)))
for m in re.finditer(r'\("(\w+)", "(\w+)", "ALTER TABLE', schema):
    tables.setdefault(m.group(1), set()).add(m.group(2))
check(len(tables) > 200 and "ical_token_hash" in tables.get("users", ()), f"schema.py read ({len(tables)} tables)")

spec = importlib.util.spec_from_file_location("accessways", os.path.join(ROOT, "kalmido", "accounts", "accessways.py"))
aw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aw)  # pure data, no imports of the app
WAYS, NOT = aw.ACCESS_WAYS, aw.ACCESS_NOT

named = {}
for w in WAYS:
    for t in w["tables"]:
        named[t] = w["key"]

# 1. every key column is accounted for
need = set()
for t, cols in tables.items():
    for c in cols:
        if c in KEYS or c.endswith("_token_hash"):
            if f"{t}.{c}" not in ACCOUNT:
                need.add(t if t != "users" else f"{t}.{c}")
missing = sorted(x for x in need if x not in named and x.split(".")[0] not in named and x not in NOT)
for x in missing:
    check(False, f"{x}: holds a key but is neither a row of ACCESS_WAYS nor in ACCESS_NOT (kalmido/accounts/accessways.py): "
                 "does a new password end it (sql / fn), switch it off, or does it stay (why)?")
check(not missing, f"every table with a key column is in ACCESS_WAYS or ACCESS_NOT ({len(need)})")

# 1b. every column with an address outside, every target inside sealed data
def _covered(x):
    t = x.split(".")[0]
    return x in named or t in named or x in NOT or t in NOT


outs = sorted(f"{t}.{c}" for t, cols in tables.items() for c in cols if OUT.search(c) and not OUT_NO.search(c))
check(len(outs) > 20 and "webhooks.url" in outs and "hub_mailboxes.smtp_host" in outs, f"columns with an address outside read ({len(outs)})")
for x in outs:
    if not _covered(x):
        check(False, f"{x}: an address outside but neither a row of ACCESS_WAYS nor in ACCESS_NOT (kalmido/accounts/accessways.py): "
                     "does data of the account go there - then a row (password, mail, what a new password does) - or why not?")
check(all(_covered(x) for x in outs), f"every column with an address outside is in ACCESS_WAYS or ACCESS_NOT ({len(outs)})")
for x, what in SEALED.items():
    t, _, c = x.partition(".")
    check(t in tables and c in tables[t], f"{x}: the sealed column exists ({what})")
    check(x in named, f"{x}: {what} is a row of ACCESS_WAYS")

# 2. nothing stale
for x in sorted(set(named) | set(NOT)):
    t, _, c = x.partition(".")
    check(t in tables and (not c or c in tables[t]), f"{x}: named in accessways.py and in the schema")
check(not (set(named) & set(NOT)), f"nothing in ACCESS_WAYS and ACCESS_NOT at once {sorted(set(named) & set(NOT))}")
keys = [w["key"] for w in WAYS]
check(len(keys) == len(set(keys)), "every row key once")
for t, why in NOT.items():
    check(isinstance(why, str) and why.strip(), f"{t}: ACCESS_NOT needs a reason")

# 3. the rows
sec = ast.parse(open(os.path.join(ROOT, "kalmido", "accounts", "secmail.py"), encoding="utf-8").read())
events = {k.value for n in sec.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "SEC_EVENTS" for k in n.value.keys}
check("out_new" in events and "token_new" in events, f"SEC_EVENTS read ({len(events)})")
for w in WAYS:
    k, end = w["key"], w["end"]
    check(end in ("session", "always", "tick", "off", "stays"), f"{k}: a known end ({end})")
    check(isinstance(w.get("what", w.get("why")), str), f"{k}: says what it is")
    if end == "stays":
        check(bool((w.get("why") or "").strip()) and not w.get("sql") and not w.get("fn"), f"{k}: stays with a reason and ends nothing")
    if end in ("always", "tick", "off"):
        check(bool(w.get("sql") or w.get("fn")), f"{k}: ends through sql or fn")
    for q in w.get("sql", ()):
        check(q.count("?") == 1, f"{k}: every statement takes the uid once: {q[:60]}")
    if end == "off":
        # #7633 F1: a flow's webhook keeps the reason in hook_state and its waiting calls go 'off' (doc_flow_runs is the history)
        check(any(q.lstrip().startswith("UPDATE") and re.search(r"(disabled_reason|hook_state)='password'", q) for q in w.get("sql", ())) and
              any(("queue" in q and q.lstrip().startswith("DELETE")) or ("doc_flow_runs" in q and "hook='off'" in q and "hook='wait'" in q)
                  for q in w.get("sql", ())) and not any(q.lstrip().startswith("DELETE") and "queue" not in q for q in w.get("sql", ())),
              f"{k}: switched off with the reason 'password' and its queue emptied, never deleted")
    if w.get("fn"):
        mod, fn = w["fn"].split(":")
        path = os.path.normpath(os.path.join(ROOT, "kalmido", "accounts", *([".."] * (len(mod) - len(mod.lstrip(".")) - 1)),
                                             *mod.lstrip(".").split("."))) + ".py"
        src = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        check(f"def {fn}(c, uid)" in src, f"{k}: {w['fn']} exists ({os.path.relpath(path, ROOT)})")
    if w.get("mail"):
        check(w["mail"] in events, f"{k}: its security mail {w['mail']} is in SEC_EVENTS")
for k in ("webhooks", "channels", "flow_hooks", "app_passwords", "api_tokens"):
    check(k in keys, f"the row {k} is there")

# 3b. #7633 F5: the mail out_new closes with its row's end (secmail.py SEC_OUT_END): every call names its row
ROWS = {w["key"]: w for w in WAYS}
calls = []
for path in sorted(os.path.join(d, f) for d, _, fs in os.walk(os.path.join(ROOT, "kalmido")) for f in fs if f.endswith(".py")):
    for n in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
        if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "sec_mail" \
                and any(isinstance(a, ast.Constant) and a.value == "out_new" for a in n.args):
            way = next((k.value.value for k in n.keywords if k.arg == "way" and isinstance(k.value, ast.Constant)), None)
            calls.append((os.path.relpath(path, ROOT), n.lineno, way))
check(len(calls) >= 5, f"F5: the mails out_new found ({len(calls)})")
for f, ln, way in calls:
    w = ROWS.get(way)
    check(w is not None and w["end"] in ("off", "stays"), f"F5: {f}:{ln} sec_mail out_new names its row (way={way!r}, an off or stays row)")
    if w and w["end"] == "stays":
        check(isinstance(w.get("where"), str) and w["where"].strip(), f"F5: the row {way} names where the person checks it (where)")
check(re.search(r'"where": N_\(', open(os.path.join(ROOT, "kalmido", "accounts", "accessways.py"), encoding="utf-8").read()) is not None,
      "F5: the places are marked for the translation files (N_)")
check({w for _, _, w in calls} >= {"webhooks", "channels", "flow_hooks", "mailbox", "agents"}, "F5: all five ways out tell their row")

# 3c. #7633 F6: what is off already (after failures) gets the reason 'password' too
for w in WAYS:
    if w["end"] == "off":
        up = [q for q in w.get("sql", ()) if q.lstrip().startswith("UPDATE") and "'password'" in q]
        check(up and not any(re.search(r"AND enabled\s*$|hook_state=''\s*$", q) for q in up),
              f"F6: {w['key']}: also one already switched off gets the reason 'password'")

# 4. ses_access_end reads the list
src = open(os.path.join(ROOT, "kalmido", "accounts", "sessions.py"), encoding="utf-8").read()
body = src[src.index("def ses_access_end("):]
body = body[:body.index("\ndef ", 5)]
check("ACCESS_WAYS" in body and not re.search(r"c\.execute\(\s*[\"'](DELETE|UPDATE)", body),
      "ses_access_end runs the rows of ACCESS_WAYS, no handwritten statement of its own")
check("SES_ACCESS_END" not in src, "no second registry next to the list (SES_ACCESS_END is gone)")

print(f"access_ways_test: {OKS[0]} ok, {len(FAILS)} failed", flush=True)
raise SystemExit(1 if FAILS else 0)
