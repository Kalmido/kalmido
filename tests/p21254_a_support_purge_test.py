#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1254.0 (#6294, audit #4741 Z8-F1/F4/F5): a support session deletes nothing for good on any way, reads and makes no secret
inbox address and writes into no organisation without its own support access through a child path. Own container (hosted, a
server key). Invented accounts only.
freelancer-matrix: own
tenant-matrix: support
 - the guard: every DELETE route of the server (tests/routes_ast.py reads the same source as app.url_map) whose function
   deletes for good (calls a ..._purge function, reads a delete-for-good query parameter or ends in /purge) stands in PURGE (with the query
   that makes it final) or in EXEMPT (with the reason). A route without an entry is red (a new purge route needs a decision),
   an entry without such a route too (stale). Every PURGE entry is called by a support session: 403 code support_session.
 - a person without an organisation (frida): a task into the trash stays possible, ?hard=1 on it 403 and it stays in the
   trash; a file node ?purge=1 403; the office trash's core delete for good 403; her own session deletes the task for good
 - the inbox addresses: GET /api/me/mail, GET /api/docs/mail-addresses, GET /api/lists/<id>/request-mail and PATCH
   request-mail (on / renew) 403 for the support session, fine for her own session; the address made by her own session
   stays unchanged
 - review of 2.1254.0: every GET route whose function reaches an inbox address (mail_addr / rq_address, followed through the
   functions it calls, read from the source with the imports resolved) stands in ADDR: refused for a support session (403
   support_session) or answering with the address left empty (the rest stays readable); a route without an entry is red, an entry
   without such a route too. Live: frida's own session makes the addresses and sees them, her support session gets 403 / ''
 - a member of an organisation (cara): a comment and an attachment on a task of the organisation's project and an edit of
   that task 403 without the organisation's grant, fine with it; her private task stays writable
usage: p21254_a_support_purge_test.py <datadir>"""
import ast
import glob
import os
import re
import sys

import kt
from kt import B, FAILS, OKS, check, sess

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer, login, org_join  # noqa: E402

# ---------------------------------------------------------------- the guard's table (decided per route)
# route (as in the source) -> the query that makes it delete for good ("" = the route itself)
PURGE = {
    "/api/tasks/<int:tid>": "?hard=1",
    "/api/files/nodes/<int:nid>": "?purge=1",
    "/api/notes/<int:nid>": "?empty=1",
    "/api/office/trash/core/<kind>/<int:rid>": "",
    "/api/lists/<int:lid>": "",
    "/api/obj/<kind>/<int:rid>": "",
    "/api/trash": "?all=1",
    "/api/trash/lists/<int:lid>": "",
    "/api/list-files/<int:fid>/purge": "",
    "/api/attachments/<int:aid>/purge": "",
    "/api/clients/<int:cid>/purge": "",
    "/api/orgs/<int:oid>/lists/<int:lid>": "",
    "/api/orgs/<int:oid>/invites/<ref>": "",
    "/api/videos/signoffs/orphaned/<int:sid>": "",
}
# route -> why a support session may call it although its function names a purge
EXEMPT = {
    "/api/office/letterhead": "the letterhead file stays as the one undo step (prev); only the older undo file goes",
}
# review of 2.1254.0 (#6294): GET route reaching an inbox address -> REFUSED (sga_guard) or (query, the address values of the answer)
REFUSED = "refused"
ADDR = {
    "/api/me/mail": REFUSED,
    "/api/docs/mail-addresses": REFUSED,
    "/api/lists/<int:lid>/request-mail": REFUSED,
    "/api/office/receipt-mail": REFUSED,
    "/api/office/letters/mail-info": REFUSED,
    "/api/office/letters/<int:lid>/mail-draft": REFUSED,
    "/api/office/privacy-sheets/<int:sid>/mail": REFUSED,  # the reply code of the sheet in the subject (made on the GET)
    "/api/docs/settings": ("?ws=private", lambda j: [j["mail"]["address"]]),
    "/api/hubmail/mails": ("?list_id={LID}", lambda j: [j["address"]]),  # ?client_id= takes the same _address_of
    "/api/hubmail/inbox": ("", lambda j: [x["address"] for x in j["spaces"]]),
}
ADDR_SEED = {("kalmido.integrations.mail", "mail_addr"), ("kalmido.integrations.reqmail", "rq_address")}
MARK_CALL = re.compile(r"(^|_)purge($|_)")  # obj_purge, tre_purge, fsk_purge, list_purge, user_purge, client_purge ...
MARK_ARGS = {"hard", "purge", "empty", "permanent", "forever"}


def _calls(fn):
    names, args = set(), set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            names.add(name)
            # request.args.get("hard")
            if (name == "get" and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute) and f.value.attr == "args"
                    and n.args and isinstance(n.args[0], ast.Constant)):
                args.add(n.args[0].value)
    return names, args


def purge_routes(root):
    """-> {route: reason}: the DELETE routes whose function deletes for good, read from the source (as routes_ast.py)."""
    out = {}
    for fn in [os.path.join(root, "app.py")] + sorted(glob.glob(os.path.join(root, "kalmido", "**", "*.py"), recursive=True)):
        if not os.path.exists(fn):
            continue
        tree = ast.parse(open(fn, encoding="utf-8").read(), fn)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in node.decorator_list:
                if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.args and isinstance(d.args[0], ast.Constant)):
                    continue
                meth = d.func.attr
                if meth == "route":
                    ms = [e.value for kw in d.keywords if kw.arg == "methods" for e in getattr(kw.value, "elts", []) if isinstance(e, ast.Constant)]
                    if "DELETE" not in [str(m).upper() for m in ms]:
                        continue
                elif meth != "delete":
                    continue
                names, args = _calls(node)
                hits = sorted(x for x in names if MARK_CALL.search(x)) + sorted("?" + a for a in args & MARK_ARGS)
                if "purge" in d.args[0].value.split("/"):
                    hits.append("/purge")
                if hits:
                    out[d.args[0].value] = f"{os.path.relpath(fn, root)} {node.name}: {', '.join(hits)}"
    return out


def addr_routes(root):
    """-> {GET route: the chain of calls to the address}: every function by module; a call by name followed into the function
    it names (the module's own or imported, also inside a function); the GET routes whose function reaches ADDR_SEED."""
    mods, funcs, imports, routes = {}, {}, {}, []
    for fn in [os.path.join(root, "app.py")] + sorted(glob.glob(os.path.join(root, "kalmido", "**", "*.py"), recursive=True)):
        if os.path.exists(fn):
            m = os.path.relpath(fn, root)[:-3].replace(os.sep, ".").removesuffix(".__init__")
            mods[m] = (fn.endswith("__init__.py"), ast.parse(open(fn, encoding="utf-8").read(), fn))
    for m, (pkg, tree) in mods.items():
        imp = imports.setdefault(m, {})
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom):
                base = m.split(".") if pkg else m.split(".")[:-1]
                src = ".".join(base[:len(base) - n.level + 1] + ([n.module] if n.module else [])) if n.level else n.module or ""
                imp.update({a.asname or a.name: (src, a.name) for a in n.names})
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.setdefault((m, n.name), n)
                for d in n.decorator_list:
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.args and isinstance(d.args[0], ast.Constant):
                        ms = [str(e.value).upper() for kw in d.keywords if kw.arg == "methods" for e in getattr(kw.value, "elts", []) if isinstance(e, ast.Constant)]
                        if d.func.attr == "get" or (d.func.attr == "route" and (not ms or "GET" in ms)):
                            routes.append((d.args[0].value, (m, n.name)))

    def resolve(m, name, depth=0):
        if (m, name) in funcs:
            return m, name
        src = imports.get(m, {}).get(name)
        return resolve(*src, depth + 1) if src and src[0] in mods and depth < 6 else None
    calls = {k: {r for n in ast.walk(f) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) for r in [resolve(k[0], n.func.id)] if r}
             for k, f in funcs.items()}
    via, todo = {}, True
    while todo:
        todo = False
        for k, cs in calls.items():
            hit = sorted(x for x in cs if x in ADDR_SEED or x in via)
            if hit and k not in via and k not in ADDR_SEED:
                via[k], todo = hit[0], True
    out = {}
    for r, k in routes:
        chain = [k]
        while chain[-1] in via:
            chain.append(via[chain[-1]])
        if len(chain) > 1:
            out[r] = " > ".join(x[1] for x in chain)
    return out


FOUND_ADDR = addr_routes(os.path.join(N, ".."))
check(len(FOUND_ADDR) >= 8, f"the guard finds the address routes ({len(FOUND_ADDR)})")
for r, why in sorted(FOUND_ADDR.items()):
    check(r in ADDR, f"guard: GET {r} reaches an inbox address ({why}) - refuse it for a support session (SGA_SECRET_READ / SGA_GET_REFUSED*) "
                     "or leave the address out for it (sga_is_support), and add it to ADDR")
for r in sorted(ADDR):
    check(r in FOUND_ADDR, f"guard: the entry {r} names no GET route that reaches an inbox address (stale)")

FOUND = purge_routes(os.path.join(N, ".."))
check(len(FOUND) >= 10, f"the guard finds the purge routes ({len(FOUND)})")
for r, why in sorted(FOUND.items()):
    check(r in PURGE or r in EXEMPT, f"guard: DELETE {r} deletes for good ({why}) - add it to SGA_NO_WRITE / SGA_PURGE_ARGS and PURGE, or EXEMPT with a reason")
for r in sorted(set(PURGE) | set(EXEMPT)):
    check(r in FOUND, f"guard: the entry {r} names no DELETE route that deletes for good (stale)")

KEY = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA="  # a test server key (32 bytes, base64)
# review of 2.1254.0: mail in on (an inbox address to leave out; no IMAP server: polled once an hour, failing quietly)
kt.fresh(env={"KALMIDO_SECRET_KEY": KEY, "KALMIDO_HOSTED": "1", "KALMIDO_MAIL_ADDRESS": "tasks@example.test", "KALMIDO_IMAP_HOST": "127.0.0.1",
              "KALMIDO_IMAP_PORT": "1143", "KALMIDO_IMAP_SSL": "0", "KALMIDO_IMAP_USER": "kalmido", "KALMIDO_IMAP_PASSWORD": "secret",
              "KALMIDO_IMAP_INTERVAL": "3600"}, prefix="P21254A")
assert kt.sess(None).post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "collab_all": True, "modules": ["comments"]})
A = sess("alice")
FID, _Fr = freelancer(B, A)
Fr = login(B, "frida")
assert Fr.patch(B + "/api/settings", json={"lang": "en", "tour": "done"}).ok


def support(uid, own):
    """A support session of account uid: the person grants account access, the operator makes a sign-in link."""
    assert own.post(B + "/api/support-access", json={"hours": 1}).ok
    r = A.post(B + f"/api/users/{uid}/signin-link")
    assert r.ok, r.text
    s = kt.sess(None)
    r = s.post(B + "/api/auth/link", json={"token": r.json()["link"].split("#signin/")[1]})
    assert r.ok, r.text
    return s


def refused(r):
    return r.status_code == 403 and r.headers.get("content-type", "").startswith("application/json") and r.json().get("code") == "support_session"


def code(r):
    return r.json().get("code") if r.headers.get("content-type", "").startswith("application/json") else None


def sample(route):
    return re.sub(r"<(?:int:)?[^>]+>", lambda m: "999999" if m.group(0).startswith("<int:") else "x", route)


X = support(FID, Fr)
# ---------------------------------------------------------------- every route that deletes for good
for r, q in sorted(PURGE.items()):
    res = X.delete(B + sample(r) + q)
    check(refused(res), f"support session: DELETE {sample(r)}{q} (deletes for good) -> 403 support_session, {res.status_code} {res.text[:100]}")

# ---------------------------------------------------------------- the three ways of the audit, on real objects
LID = Fr.post(B + "/api/lists", json={"name": "Garden"}).json()["id"]
TID = Fr.post(B + "/api/tasks", json={"title": "Old seeds", "list_id": LID}).json()["id"]
r = X.delete(B + f"/api/tasks/{TID}")
check(r.ok, f"support session: a task into the trash stays possible {r.status_code} {r.text[:100]}")
check(kt.dbx("SELECT deleted_at IS NOT NULL FROM tasks WHERE id=?", (TID,)) == [(True,)], "the task is in the trash")
for q in ("?hard=1", "?hard=0", "?hard="):
    r = X.delete(B + f"/api/tasks/{TID}{q}")
    check(refused(r), f"support session: DELETE task{q} 403 (the parameter decides, not its value), {r.status_code}")
check(kt.dbx("SELECT COUNT(*) FROM tasks WHERE id=?", (TID,)) == [(1,)], "the task is still there (in the trash)")
r = Fr.post(B + "/api/files/folders", json={"name": "Old"})
NID = (r.json() or {}).get("id") if r.ok else None
check(bool(NID), f"setup: frida's folder {r.status_code} {r.text[:100]}")
r = X.delete(B + f"/api/files/nodes/{NID}?purge=1")
check(refused(r), f"support session: a file node ?purge=1 403, {r.status_code}")
check(kt.dbx("SELECT COUNT(*) FROM fs_nodes WHERE id=?", (NID,)) == [(1,)], "the folder is still there")
r = X.delete(B + "/api/office/trash/core/receipt/1")
check(refused(r), f"support session: the office trash's core delete for good 403, {r.status_code}")
r = Fr.delete(B + f"/api/tasks/{TID}?hard=1")
check(r.ok and code(r) != "support_session" and kt.dbx("SELECT COUNT(*) FROM tasks WHERE id=?", (TID,)) == [(0,)],
      f"frida's own session deletes it for good {r.status_code} {r.text[:100]}")

# ---------------------------------------------------------------- the secret inbox addresses
for path in ("/api/me/mail", "/api/docs/mail-addresses", f"/api/lists/{LID}/request-mail"):
    r = X.get(B + path)
    check(refused(r), f"support session: GET {path} (secret addresses) 403, {r.status_code} {r.text[:100]}")
    r = Fr.get(B + path)
    check(code(r) != "support_session" and r.status_code < 500, f"frida's own session reads {path}: {r.status_code}")
for b in ({"on": True}, {"renew": True}, {"done_mail": True}):
    r = X.patch(B + f"/api/lists/{LID}/request-mail", json=b)
    check(refused(r), f"support session: PATCH request-mail {b} 403, {r.status_code}")
check(kt.dbx("SELECT COUNT(*) FROM hub_tokens WHERE kind='ticket' AND list_id=?", (LID,)) == [(0,)], "no request address was made")
r = Fr.patch(B + f"/api/lists/{LID}/request-mail", json={"on": True})
check(code(r) != "support_session" and r.status_code < 500, f"frida's own session switches it {r.status_code} {r.text[:100]}")

# ---------------------------------------------------------------- review of 2.1254.0: every GET route reaching an inbox address
for body_, path in (({"ws": "private"}, "/api/docs/mail"), ({"list_id": LID}, "/api/hubmail/address"), ({"ws": "private"}, "/api/hubmail/address")):
    r = Fr.post(B + path, json=body_)
    check(r.ok and "@" in (r.json().get("address") or ""), f"setup: frida's own session makes the address {path} {body_} {r.status_code} {r.text[:100]}")
for route, how in sorted(ADDR.items(), key=lambda x: x[0]):
    if how == REFUSED:
        r = X.get(B + sample(route))
        check(refused(r), f"support session: GET {sample(route)} (an inbox address) 403 support_session, {r.status_code} {r.text[:100]}")
        continue
    url = B + route + how[0].format(LID=LID)
    mine, theirs = Fr.get(url), X.get(url)
    check(mine.ok and any("@" in (a or "") for a in how[1](mine.json())), f"frida's own session sees the address of {route}: {mine.status_code} {mine.text[:150]}")
    check(theirs.ok and not any(how[1](theirs.json())), f"support session: {route} answers without the address {theirs.status_code} {theirs.text[:150]}")

# ---------------------------------------------------------------- child paths of an organisation's task
ALPHA = A.get(B + "/api/orgs").json()["orgs"][0]["id"]
r = A.post(B + "/api/users", json={"username": "carl", "display_name": "Carl", "password": "password123", "email": "carl@example.com"})
assert r.ok, r.text
CARL = r.json()["id"]
r = A.post(B + "/api/users", json={"username": "cara", "display_name": "Cara", "password": "password123", "email": "cara@example.com",
                                   "orgs": [{"id": ALPHA, "role": "member"}]})
assert r.ok, r.text
CID = r.json()["id"]
Ca, Cc = login(B, "carl"), login(B, "cara")
for s in (Ca, Cc):
    assert s.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": "comments,collab"}).ok
r = Ca.post(B + "/api/orgs", json={"name": "Client Studio"})
assert r.status_code == 201, r.text
CO = r.json()["id"]
kt.dbx("INSERT INTO conn_links(a_id, b_id, created_at) VALUES(?, ?, '2026-01-01T00:00:00Z')", tuple(sorted((CARL, CID))))
kt.proved()
assert Ca.put(B + f"/api/orgs/{CO}/members", json={"email": "cara@example.com"}).ok
assert org_join(B, "cara", CO)
OL = Cc.post(B + "/api/lists", json={"name": "Studio project", "org_id": CO}).json()["id"]
OT = Cc.post(B + "/api/tasks", json={"title": "Studio task", "list_id": OL}).json()["id"]
PL = Cc.post(B + "/api/lists", json={"name": "Cara private"}).json()["id"]
PT = Cc.post(B + "/api/tasks", json={"title": "Private task", "list_id": PL}).json()["id"]
Y = support(CID, Cc)
WAYS = (("a comment", lambda s, t: s.post(B + f"/api/tasks/{t}/comments", json={"body": "From support"})),
        ("an attachment", lambda s, t: s.post(B + f"/api/tasks/{t}/attachments", files={"file": ("note.txt", b"help\n", "text/plain")})),
        ("an edit", lambda s, t: s.patch(B + f"/api/tasks/{t}", json={"title": "Edited by support"})))
for what, call in WAYS:
    r = call(Y, OT)
    check(refused(r), f"support session: {what} on the organisation's task without its grant 403, {r.status_code} {r.text[:100]}")
    r = call(Y, PT)
    check(r.ok and code(r) != "support_session", f"support session: {what} on her private task {r.status_code} {r.text[:100]}")
check(kt.dbx("SELECT COUNT(*) FROM attachments WHERE task_id=?", (OT,)) == [(0,)] and kt.dbx("SELECT title FROM tasks WHERE id=?", (OT,)) == [("Studio task",)],
      "nothing went into the organisation's task")
assert Ca.post(B + "/api/support-access", json={"hours": 1, "org_id": CO}).ok
for what, call in WAYS:
    r = call(Y, OT)
    check(r.ok and code(r) != "support_session", f"with the organisation's own support access: {what} {r.status_code} {r.text[:100]}")

print(f"p21254_a: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
