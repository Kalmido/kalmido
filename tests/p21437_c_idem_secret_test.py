#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.1437.0 C (#6558): the idempotency store (kalmido/core/idem.py) keeps no secret and no needless text. No container needed.
 1. guard over all write routes: a route whose answer carries a field named like a secret (token, secret, code, key, password,
    recovery_codes ...) with a computed value sets g.idem_no_body (its answer is never kept) -- or stands in WAIVED with a
    reason (an error answer's code, a layout's key); routes that hand out a secret through a helper stand in VIA_HELPER
 2. IDEM_FULL: the app's offline routes (tasks, habits, time, notes, chat) keep their whole answer, everything else not
 3. idem_body: the short answer in the shape of the original (ok, id fields, updated_at); an answer with a secret field keeps
    only its short answer even on IDEM_FULL; a marked route (no_body) keeps nothing; over IDEM_MAX_BODY the short answer
usage: python3 tests/p21437_c_idem_secret_test.py"""
import ast
import glob
import json
import os
import re
import sys

N = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(N, "..")
sys.path.insert(0, N)
from kt import check, done  # noqa: E402

IDEM = os.path.join(ROOT, "kalmido", "core", "idem.py")
SRC = open(IDEM, encoding="utf-8").read()
NS = {"re": re, "json": json}
for n in ast.parse(SRC).body:  # the pure parts of idem.py, without the app (its import needs the server's config)
    if (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in ("IDEM_FULL", "IDEM_NET", "IDEM_MAX_BODY", "_IDEM_ID", "_IDEM_KEEP", "_IDEM_SECRET") for t in n.targets)) \
            or (isinstance(n, ast.FunctionDef) and n.name in ("idem_secretish", "idem_short", "idem_body")):
        exec(compile(ast.Module([n], []), IDEM, "exec"), NS)  # noqa: S102 (our own source)
SEC = NS["_IDEM_SECRET"]
W = {"post", "patch", "put", "delete"}
# (file, function): a secret-named field in the answer that is no secret -- why
WAIVED = {
    ("kalmido/accounts/cinvite.py", "cinv_check"): "min_password = the shortest password allowed (a number)",
    ("kalmido/accounts/invite.py", "invite_check"): "min_password = the shortest password allowed (a number)",
    ("kalmido/accounts/layoutsets.py", "lyv_activate_route"): "key = the name of a saved view",
    ("kalmido/accounts/layoutsets.py", "lyv_standard"): "key = the name of a saved view",
    ("kalmido/office/fints.py", "_fnt_test_conn"): "code = the bank's answer code of a test connection",
    ("kalmido/office/payonline.py", "pol_check"): "code = the error code of a failed check (ok false)",
}
# routes that hand out a secret through a helper (the scan does not see into it)
VIA_HELPER = {
    ("kalmido/accounts/login.py", "auth_enrol_totp"), ("kalmido/accounts/login.py", "me_totp_begin"),  # totp_payload
    ("kalmido/agents/setup.py", "ains_my_code"), ("kalmido/agents/setup.py", "ains_admin_code"),  # ains_code_new
    ("kalmido/core/orgcrypt.py", "oc_route_recovery"),  # the recovery key
}
MARKED_FILES = ("kalmido/api/v1.py", "kalmido/integrations/webhooks.py", "kalmido/integrations/git.py")  # since 2.391.0 (#3362)


def write_paths(fn):
    out = []
    for d in fn.decorator_list:
        if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and getattr(d.func.value, "id", "") == "app"
                and d.args and isinstance(d.args[0], ast.Constant) and str(d.args[0].value).startswith("/api/")):
            continue
        if d.func.attr == "route":
            ms = [k for k in d.keywords if k.arg == "methods"]
            if not ms or not any(isinstance(e, ast.Constant) and str(e.value).lower() in W for e in getattr(ms[0].value, "elts", [])):
                continue
        elif d.func.attr not in W:
            continue
        out.append(d.args[0].value)
    return out


def answered(fn):
    """The values a route answers with: return values and jsonify(...) calls."""
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and n.value is not None:
            yield n.value
        elif isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "jsonify":
            yield n


def secret_fields(fn):
    hits = set()
    for v in answered(fn):
        for n in ast.walk(v):
            if isinstance(n, ast.Call):
                name = getattr(n.func, "id", getattr(n.func, "attr", ""))
                kw = {k.arg for k in n.keywords}
                if name in ("err", "BadInput", "Denied", "get", "execute", "sorted", "min", "max") or "error" in kw:
                    continue  # an error answer (never stored) or no answer field at all
                hits |= {k.arg for k in n.keywords if k.arg and SEC.search(k.arg.lower()) and not isinstance(k.value, ast.Constant)}
            if isinstance(n, ast.Dict) and not any(isinstance(k, ast.Constant) and k.value == "error" for k in n.keys):
                hits |= {k.value for k, x in zip(n.keys, n.values) if isinstance(k, ast.Constant) and isinstance(k.value, str)
                         and SEC.search(k.value.lower()) and not isinstance(x, ast.Constant)}
    return hits


# ---- 1. the guard over all write routes
found, marked, seen = [], set(), set()
for p in sorted(glob.glob(os.path.join(ROOT, "kalmido", "**", "*.py"), recursive=True)):
    rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
    src = open(p, encoding="utf-8").read()
    for fn in ast.walk(ast.parse(src)):
        if not isinstance(fn, ast.FunctionDef) or not write_paths(fn):
            continue
        has = "idem_no_body" in (ast.get_source_segment(src, fn) or "")
        if has:
            marked.add((rel, fn.name))
        if (h := secret_fields(fn)) and not has:
            seen.add((rel, fn.name))
            if (rel, fn.name) not in WAIVED:
                found.append(f"{rel}:{fn.lineno} {fn.name} {sorted(h)}")
check(not found, "#6558: every write route that answers with a secret sets g.idem_no_body (or stands in WAIVED with a reason): "
      + "; ".join(found))
check(len(marked) >= 25, f"#6558: the marked routes are found ({len(marked)})")
check(not (set(WAIVED) - seen), f"#6558: no stale WAIVED entry {sorted(set(WAIVED) - seen)}")
check(not (VIA_HELPER - marked), f"#6558: the routes with a secret from a helper are marked {sorted(VIA_HELPER - marked)}")
for rel in MARKED_FILES:  # tokens and webhook secrets of API v1 / git (2.391.0): their marks stay
    check("g.idem_no_body = True" in open(os.path.join(ROOT, rel), encoding="utf-8").read(), f"#3362: {rel} keeps its idem_no_body")

# ---- 2. which routes keep their whole answer
FULL = NS["IDEM_FULL"]
for p in ("/api/tasks", "/api/tasks/5", "/api/tasks/batch", "/api/habits/3/log", "/api/time/start", "/api/time/entries/9",
          "/api/notes/4", "/api/lists/2/notes", "/api/team/messages", "/api/v1/tasks/7/complete", "/api/v1/agent/chats/3/messages"):
    check(FULL.match(p), f"#6558: {p} keeps its whole answer")
for p in ("/api/lists", "/api/office/offers/3", "/api/v1/office/offers/3", "/api/me/tokens", "/api/wiki/pages/3", "/api/taskscopes",
          "/api/contacts", "/api/v1/docs/5", "/api/my/agents/3/token", "/api/me/drop-token", "/api/life/journal/2026-11-19",
          "/api/time/sheets", "/api/time/sheets/decide", "/api/v1/time/sheets"):
    check(not FULL.match(p), f"#6558: {p} keeps only the short answer")

# ---- 3. the text kept
body, short = NS["idem_body"], NS["idem_short"]
J = lambda v: json.dumps(v).encode()  # noqa: E731
check(body("/api/tasks", b'{"id":5,"title":"Milk"}') == '{"id":5,"title":"Milk"}', "a task: the whole answer")
offer = {"ok": True, "offer": {"id": 3, "customer": "Anna", "updated_at": "t1", "positions": [{"id": 1, "text": "Fee"}, {"text": "x"}]},
         "contact_id": 4, "ids": [1, 2], "note": "private"}
got = json.loads(body("/api/v1/office/offers/3", J(offer)))
check(got == {"ok": True, "offer": {"id": 3, "updated_at": "t1", "positions": [{"id": 1}]}, "contact_id": 4, "ids": [1, 2]},
      f"an office draft: the short answer in its shape {got}")
check(json.loads(body("/api/lists", J({"id": 9, "name": "Plans"}))) == {"ok": True, "id": 9}, "a list: ok + id")
check(json.loads(body("/api/x", J([{"id": 1, "a": 2}, {"b": 3}]))) == [{"id": 1}], "a list answer: its ids")
for path, ans, word in (("/api/docs/scan-keys", {"id": 1, "name": "n", "code": "KSK-abc"}, "KSK-abc"),
                        ("/api/tasks", {"id": 1, "token": "tok-secret"}, "tok-secret"),
                        ("/api/notes/2", {"id": 2, "x": {"recovery_codes": ["aaaa-bbbb"]}}, "aaaa-bbbb"),
                        ("/api/admin/agents", {"id": 3, "webhook_secret": "whsec_1", "token": "abk_1"}, "whsec_1")):
    t = body(path, J(ans))
    check(t is not None and word not in t and json.loads(t).get("id") == ans["id"], f"a secret field on {path}: only the short answer {t}")
check(body("/api/me/tokens", J({"id": 1, "token": "abk_x"}), True) is None, "a marked route (idem_no_body): nothing kept")
check(body("/api/tasks", b"not json") is None, "no JSON: nothing kept")
big = {"id": 7, "items": [{"id": i, "t": "x" * 200} for i in range(2000)]}
t = body("/api/tasks/batch", J(big))
check(t is not None and len(t) < NS["IDEM_MAX_BODY"] and json.loads(t)["items"][5] == {"id": 5}, "over IDEM_MAX_BODY: the short answer (ids kept)")
check(body("/api/tasks/batch", J({"ok": True, "conflicts": [], "code": None})) is not None
      and "conflicts" in body("/api/tasks/batch", J({"ok": True, "conflicts": [], "code": None})), "a null code is no secret")
# #7494 review F1: the app's own key on every write ("n." + ..., rawFetch0) keeps only the short answer, also on IDEM_FULL:
# a timesheet decision's note (sealed in time_sheets.note) never lies in idem_keys as plain text
sheet = {"ok": True, "review": [{"id": 4, "user_id": 2, "name": "Anna", "hours": 7.5, "note": "sealed text"}]}
t = body("/api/time/sheets/decide", J(sheet), False, NS["IDEM_NET"] + "k1")
check(t is not None and "sealed text" not in t and "Anna" not in t and json.loads(t)["review"][0]["id"] == 4, f"#7494: an n. key keeps only the short answer {t}")
t = body("/api/time/sheets/decide", J(sheet), False, "k-of-api")
check(t is not None and "sealed text" not in t, f"#7494 review F1: a timesheet decision keeps only its short answer with any key {t}")
check("x1" in body("/api/time/entries/9", J({"id": 9, "note": "x1"}), False, "outbox-k1"), "#7494: an outbox key on IDEM_FULL keeps the whole answer as before")
src = open(os.path.join(ROOT, "static", "js", "core.js"), encoding="utf-8").read()
check("'n.' + outKey()" in src and NS["IDEM_NET"] == "n.", "#7494: rawFetch0's own key carries the prefix idem.py knows (IDEM_NET)")
check("left(k, ?)=?" in SRC and "IDEM_NET_S" in SRC, "#7494 review F3: idem_prune drops the n. keys after IDEM_NET_S")
check(short({"ok": False}) == {"ok": False} and short("x") is None, "short: ok kept, a bare text is nothing")
sys.exit(done("p21437_c_idem_secret"))
