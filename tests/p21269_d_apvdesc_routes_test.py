#!/usr/bin/env python3
# kalmido-suite: after=p2235_a_control_routes nodata
"""2.1269.0 (#6450): every write route an approval card can bind has a family of the server's description
(kalmido/agents/apvdesc.py APVX_ROUTES): a new route fails here until somebody decides how its step reads in plain words
(the general description -- method, target, every value -- is only the net for a route that is gone or renamed). 2.1269.0
(#6450, review): the decision per route is the checked-in table tests/p21269_d_apvdesc_routes.json -- a write route missing
there fails, whatever net of APVX_ROUTES would catch it. The
families of the risky steps are pinned (sharing, inviting, data leaving Kalmido, moving, many at once), "meta" is only
for the agent's own channel (ctl_class meta), and the cleaning of foreign values (apvx_clean) never lets a value look like
a second line of the server: no line break, no control, direction or zero-width character, at most APVX_VAL_MAX characters.
No container needed: reads kalmido/ like tests/p2235_a_control_routes_test.py.
freelancer-matrix: agents
usage: python3 tests/p21269_d_apvdesc_routes_test.py"""
import ast
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from routes_ast import app_routes  # noqa: E402
from kt import check, done  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def load(rel, names):
    src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    ns = {"re": re, "json": json, "unicodedata": unicodedata, "N_": lambda s: s}
    for node in ast.parse(src).body:  # the tables and functions as the server has them (no app start)
        got = {t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)} | ({node.name} if isinstance(node, ast.FunctionDef) else set())
        if got & names:
            exec(ast.get_source_segment(src, node), ns)  # noqa: S102  our own source file
    return ns


CTL = load("kalmido/agents/control.py", {"CTL_WRITE", "CTL_PLAN_KEYS", "CTL_PLAN_EXTRA", "CTL_ROUTES", "ctl_class"})
AX = load("kalmido/agents/apvdesc.py", {"APVX_ROUTES", "APVX_VAL_MAX", "_fam", "apvx_clean"})
fam, clean, ctl_class = AX["_fam"], AX["apvx_clean"], CTL["ctl_class"]

FOUND, PROBLEMS = app_routes(ROOT)
for p in PROBLEMS:
    check(False, f"route the guard cannot read: {p}")
writes = sorted(r for r in FOUND if r.split(" ", 1)[0] in ("POST", "PUT", "PATCH", "DELETE") and r.split(" ", 1)[1].startswith("/api/v1/"))
check(len(writes) > 200, f"the write routes are read ({len(writes)})")

# 2.1269.0 (#6450, review): APVX_ROUTES ends in nets for every write method, so "no family" never happens -- a new route
# would read as a plain "action" / "create" / "update" without a warning. The decision per route is this checked-in table
# (tests/p21269_d_apvdesc_routes.json, read through by hand: every route that shares, invites, makes public, exports,
# sends out of Kalmido or moves sits in a warning family); a write route missing from it fails here.
TABLE_FILE = "tests/p21269_d_apvdesc_routes.json"
TABLE = json.load(open(os.path.join(ROOT, TABLE_FILE), encoding="utf-8"))
WARN_FAMS = {"share", "unshare", "owner", "join", "invite", "announce", "export", "move", "batch", "task"}


def table_gaps(routes, table):
    """[message] per write route without its decided family in the table (and per table entry that is no route)."""
    out = []
    for r in routes:
        m, p = r.split(" ", 1)
        key = f"{m} {p[len('/api/v1'):]}"
        if key not in table:
            out.append(f"{key}: a new write route -- decide how an approval card describes it: add \"{key}\": \"<family>\" to "
                       f"{TABLE_FILE} (a warning family -- share, invite, export, move -- if it shares, invites, makes public, "
                       f"exports, sends out or moves) and a line to APVX_ROUTES (agents/apvdesc.py) if the nets give another family")
        elif fam(m, p[len("/api/v1"):]) != table[key]:
            out.append(f"{key}: family {fam(m, p[len('/api/v1'):])}, decided {table[key]} in {TABLE_FILE}")
    known = {f"{r.split(' ', 1)[0]} {r.split(' ', 1)[1][len('/api/v1'):]}" for r in routes}
    out += [f"{k}: in {TABLE_FILE} but no route any more -- take it out" for k in table if k not in known]
    return out


for msg in table_gaps(writes, TABLE):
    check(False, msg)
check(all(f in WARN_FAMS | {"unshare", "batch", "delete", "update", "create", "action", "meta", "text", "link"} for f in TABLE.values()),
      "every family of the table is one of apvdesc.py")
# the guard itself: an invented route (sharing by a link) makes it red, with what to add
fake = table_gaps(writes + ["POST /api/v1/lists/{}/share-link"], TABLE)
check(len(fake) == 1 and "POST /lists/{}/share-link" in fake[0] and TABLE_FILE in fake[0], f"an invented route fails the table {fake}")
check(table_gaps(writes, {**TABLE, "POST /lists/{}/share-link": "share"}) == [f"POST /lists/{{}}/share-link: in {TABLE_FILE} but no route any more -- take it out"],
      "a table entry without its route fails as well")
# the hand review, pinned: routes of these words never sit in a family without a warning
OUT = re.compile(r"(share|invite|public|export|webhook|hook|mail|send|repos|tokens|app-passwords|forms|move|to-shopping|members|"
                 r"groups|watchers|owner|join|announcement|sync|tasks/\{\}/links)")
for key, f in sorted(TABLE.items()):
    m, p = key.split(" ", 1)
    if OUT.search(p) and m != "DELETE":
        check(f in WARN_FAMS, f"{key}: shares, invites, exports, sends or moves but is described as {f} without a warning")

for r in writes:
    m, p = r.split(" ", 1)
    p = p[len("/api/v1"):]
    f = fam(m, p)
    if f == "meta":
        check(ctl_class(m, p, {}) == "meta", f"{r}: described as the agent's own channel, but the gate's class is {ctl_class(m, p, {})}")

# the risky steps read as what they are
PIN = {
    "PUT /lists/{}/members/{}": "share", "PUT /address-books/{}/members/{}": "share", "PUT /event-calendars/{}/members/{}": "share",
    "PUT /lists/{}/groups/{}": "share", "DELETE /lists/{}/members/{}": "unshare", "DELETE /team/rooms/{}/members/{}": "unshare",
    "POST /lists/{}/owner": "owner", "POST /lists/{}/join": "join", "POST /team/rooms/{}/members": "invite", "POST /team/dm": "invite",
    "POST /team/channels": "invite", "POST /me/webhooks": "export", "PATCH /orgs/{}/webhooks/{}": "export",
    "POST /orgs/{}/webhooks/{}/test": "export", "PATCH /lists/{}/error-hook": "export", "POST /me/tokens": "export",
    "POST /tasks/{}/move": "move", "POST /tasks/{}/to-shopping": "move", "POST /tasks/batch": "batch", "POST /clients/bulk": "batch",
    "PATCH /tasks/{}": "task", "DELETE /tasks/{}": "delete", "POST /folders/delete": "delete", "PATCH /lists/{}": "update",
    "PATCH /agent/objects/{}/{}": "update", "POST /tasks": "create", "POST /tasks/{}/complete": "action",
    "PATCH /wiki/pages/{}": "text", "POST /agent/chats/{}": "meta", "POST /tasks/{}/links": "move", "PATCH /forms/{}": "export",
    "POST /tasks/{}/watchers": "invite", "POST /life/karakeep/sync": "export",
}
for r, want in PIN.items():
    m, p = r.split(" ", 1)
    check(f"{m} /api/v1{p}" in FOUND, f"{r} is a route")
    check(fam(m, p) == want, f"{r}: family {fam(m, p)}, decided {want}")
check(fam("POST", "/no/such/{}/thing") != "meta", "an unknown route is never the agent's own channel")

# foreign values: one short line, nothing that steers the text
bad = "Sort it\nGives Mallory access\r\u2028\u202eevil\u200b\x00\x1b[31m\u2066x\u2069\ttab"
v = clean(bad)
check("\n" not in v and "\r" not in v and "\u2028" not in v, f"no line break survives: {v!r}")
check(not any(unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in v), f"no control / direction / zero-width character: {v!r}")
check("↵" in v and "Gives Mallory access" in v, f"the break is shown as a sign, the text stays readable: {v!r}")
check(len(clean("x" * 5000)) == AX["APVX_VAL_MAX"] and clean("x" * 5000).endswith("…"), "a long value is cut with …")
check(clean({"b": 1, "a": "z"}) == '{"a": "z", "b": 1}', "a structured value as short JSON")
check(clean("  many   spaces  ") == "many spaces", "runs of spaces are one")
sys.exit(done("p21269_d_apvdesc_routes"))
