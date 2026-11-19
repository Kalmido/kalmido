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
 - 2.1397.0 (#6320, the check in the core instead of SGA_PATH_ORG): the guard walks every writing route (POST / PUT / PATCH /
   DELETE, tests/routes_ast.py) of an organisation-bound object (a project, a task, a section, a comment, an attachment, a
   notepad, a file node) with the organisation's object in the path as cara's support session without the organisation's
   grant: never 2xx (ALLOW names the exceptions with a reason) and nothing of the organisation changed (a fingerprint of the
   rows); the multi-select (/api/tasks/batch: patch, complete, delete, a move into the organisation's project) and the drag
   (/api/tasks/reorder, also into the project) change nothing there
 - review #4788 (2): deleting a budget receipt, a notepad and the last way of an office document (no trash: for good) 403
   support_session for frida's support session, the document stays; her own session deletes it
 - review #4788 (3): a filed mail of frida: her support session sees its recipients without the secret filing address and
   without the .eml (eml_id none, GET of its content 403 support_session, not in a ZIP); her own session sees both
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

# ---------------------------------------------------------------- 2.1397.0 (#6320, review #4788 (2)): deleting for good without a trash
for path in ("/api/budget/files/999999", "/api/notepads/999999"):
    r = X.delete(B + path)
    check(refused(r), f"support session: DELETE {path} (no trash: for good) 403 support_session, {r.status_code} {r.text[:100]}")
assert Fr.put(B + "/api/office/settings", json={"company_fields": {"name": "Frida Film", "street": "Teststrasse 1", "zip": "20000",
                                                                  "city": "Hamburg", "country": "DE"}}).ok
r = Fr.post(B + "/api/clients", json={"name": "Example Client Ltd", "street": "Marktstrasse 5", "zip": "50000", "city": "Koeln", "country": "DE"})
assert r.ok, r.text
r = Fr.post(B + "/api/office/docs", json={"kind": "invoice", "client_id": r.json()["id"], "service_from": "2026-03-01", "service_to": "2026-03-02",
                                          "items": [{"title": "Schnitt", "qty": 1, "rate": 120}]})
check(r.status_code == 201, f"setup: frida's invoice draft {r.status_code} {r.text[:150]}")
DOC = r.json().get("id") if r.status_code == 201 else 0
kt.dbx("UPDATE office_docs SET status='paid' WHERE id=?", (DOC,))  # past draft, never finalised nor sent: the last way deletes the row for good
r = X.delete(B + f"/api/office/docs/{DOC}")
check(refused(r) and kt.dbx("SELECT COUNT(*) FROM office_docs WHERE id=?", (DOC,)) == [(1,)],
      f"support session: the last way of deleting an office document (for good) 403, the document stays {r.status_code} {r.text[:100]}")
r = Fr.delete(B + f"/api/office/docs/{DOC}")
check(r.ok and kt.dbx("SELECT COUNT(*) FROM office_docs WHERE id=?", (DOC,)) == [(0,)], f"frida's own session deletes it {r.status_code} {r.text[:100]}")

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

# ---------------------------------------------------------------- review #4788 (3): a filed mail's recipients and its .eml
r = Fr.post(B + "/api/files/upload", data={"space": "private"}, files={"file": ("mail.eml", b"Subject: invented\n\nhello\n", "message/rfc822")})
check(r.ok, f"setup: frida's .eml {r.status_code} {r.text[:100]}")
EML = ((r.json().get("items") or [{}])[0].get("id") or 0) if r.ok else 0
TOKADDR = "tasks+a1b2c3d4@example.test"
HM = kt.dbx("INSERT INTO hub_mails(owner_id, list_id, ws, message_id, from_addr, to_addrs, subject, eml_id, created_at) "
            "VALUES(?, ?, ?, '<p21254@example.com>', 'sender@example.com', ?, 'Invented', ?, '2026-03-01T10:00:00Z') RETURNING id",
            (FID, LID, f"u{FID}", f"Frida <{TOKADDR}>, office@example.com", EML))[0][0]
kt.dbx("UPDATE fs_nodes SET hub_mail_id=? WHERE id=?", (HM, EML))
mine, theirs = Fr.get(B + f"/api/hubmail/mails/{HM}"), X.get(B + f"/api/hubmail/mails/{HM}")
check(mine.ok and TOKADDR in mine.json().get("to", "") and mine.json().get("eml_id") == EML,
      f"frida's own session sees the filing address and the .eml {mine.status_code} {mine.text[:200]}")
check(theirs.ok and TOKADDR not in theirs.text and "office@example.com" in theirs.json().get("to", "") and theirs.json().get("eml_id") is None,
      f"support session: the recipients without the filing address, no .eml {theirs.status_code} {theirs.text[:200]}")
for path in (f"/api/hubmail/mails/{HM}/files/{EML}", f"/api/files/nodes/{EML}/content"):
    r = X.get(B + path)
    check(refused(r), f"support session: GET {path} (the .eml) 403 support_session, {r.status_code} {r.text[:100]}")
    r = Fr.get(B + path)
    check(r.ok and b"invented" in r.content, f"frida's own session opens {path}: {r.status_code}")


def zip_names(r):
    import io
    import zipfile
    try:
        return zipfile.ZipFile(io.BytesIO(r.content)).namelist() if r.ok else []
    except zipfile.BadZipFile:
        return []


r = X.get(B + f"/api/files/zip?ids={EML}")
check("mail.eml" not in zip_names(r) and r.status_code < 500, f"support session: the .eml stays out of a ZIP {r.status_code} {zip_names(r)}")
r = Fr.get(B + f"/api/files/zip?ids={EML}")
check(r.ok, f"frida's own session downloads it as a ZIP {r.status_code} {r.text[:80] if not r.ok else ''}")
# 2.1412.0 (#7140, review of job/5474 F1): the wiki export took the .eml along (it read the file without the check); the check
# sits in fs_read now, the one reader of every route, export and ZIP
r = Fr.post(B + "/api/wiki/pages", json={"space": "private", "path": "Mails p21254", "body": f"[Mail](/api/files/nodes/{EML}/content)"})
check(r.ok, f"setup: frida's page links the .eml {r.status_code} {r.text[:120]}")
r = X.get(B + "/api/wiki/export", params={"space": "private"})
check(r.ok and not [n for n in zip_names(r) if n.endswith(".eml")], f"#7140: support session - the wiki export leaves the .eml out {r.status_code} {zip_names(r)}")
r = Fr.get(B + "/api/wiki/export", params={"space": "private"})
check(any(n.endswith("mail.eml") for n in zip_names(r)), f"#7140: frida's own wiki export takes it along {zip_names(r)}")

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
# ---------------------------------------------------------------- 2.1397.0 (#6320): every writing route of an organisation's object
import routes_ast  # noqa: E402

r = Cc.post(B + f"/api/tasks/{OT}/comments", json={"body": "From cara"})
assert r.ok, r.text
CMT = kt.dbx("SELECT MAX(id) FROM obj_comments")[0][0]
r = Cc.post(B + f"/api/tasks/{OT}/attachments", files={"file": ("a.txt", b"cara\n", "text/plain")})
assert r.ok, r.text
ATT = kt.dbx("SELECT MAX(id) FROM attachments WHERE task_id=?", (OT,))[0][0]
r = Cc.post(B + "/api/sections", json={"list_id": OL, "name": "Studio part"})
check(r.ok, f"setup: a section of the organisation's project {r.status_code} {r.text[:100]}")
SEC = (kt.dbx("SELECT MAX(id) FROM sections WHERE list_id=?", (OL,)) or [(None,)])[0][0] or 999999
r = Cc.post(B + f"/api/lists/{OL}/notepads", json={"title": "Studio pad", "body": "x"})
NP = (kt.dbx("SELECT MAX(id) FROM list_notepads WHERE list_id=?", (OL,)) or [(None,)])[0][0] or 999999
r = Cc.post(B + "/api/files/folders", json={"name": "Studio files", "org_id": CO, "space": f"org:{CO}"})
NODE = (kt.dbx("SELECT MAX(id) FROM fs_nodes WHERE org_id=?", (CO,)) or [(None,)])[0][0] or 999999
OBJ = {"lists": OL, "tasks": OT, "sections": SEC, "comments": CMT, "attachments": ATT, "notepads": NP, "files/nodes": NODE}
check(all(OBJ.values()), f"setup: the organisation's objects {OBJ}")
# route -> why a support session may get 2xx there (nothing of the organisation changes)
ALLOW = {}
TABLES = [x[0] for x in kt.dbx("SELECT table_name FROM information_schema.columns WHERE table_schema=current_schema() AND column_name='list_id'")]


def fingerprint():
    """The organisation's rows: its project and task as they are, and how many rows of every table point at the project."""
    out = [kt.dbx("SELECT * FROM lists WHERE id=?", (OL,)), kt.dbx("SELECT * FROM tasks WHERE list_id=? ORDER BY id", (OL,)),
           kt.dbx("SELECT id, body, deleted_at FROM obj_comments WHERE id=?", (CMT,)), kt.dbx("SELECT id, deleted_at FROM attachments WHERE task_id=?", (OT,)),
           kt.dbx("SELECT id, name, deleted_at FROM fs_nodes WHERE org_id=? ORDER BY id", (CO,))]
    for t in sorted(set(TABLES)):
        out.append((t, kt.dbx(f"SELECT COUNT(*) FROM {t} WHERE list_id=?", (OL,))))
    return out


before = fingerprint()
routes, _probs = routes_ast.app_routes(os.path.join(N, ".."))
walked, sup = 0, 0
for rt in sorted(routes):
    meth, path = rt.split(" ", 1)
    if meth not in ("POST", "PUT", "PATCH", "DELETE"):
        continue
    area = next((a for a in sorted(OBJ, key=len, reverse=True) if path.startswith(f"/api/{a}/{{}}")), None)
    if area is None:
        continue
    url = path.replace("{}", str(OBJ[area]), 1).replace("{}", "999999")
    res = Y.request(meth, B + url, json={})
    walked += 1
    sup += refused(res)
    check(res.status_code >= 300 or rt in ALLOW, f"guard: {rt} as a support session on the organisation's {area} without its grant -> {res.status_code} "
                                                  f"{res.text[:120]} (refuse it in the core: need_list / need_task / obj_need / need_node)")
check(walked >= 150, f"guard: the writing routes of the organisation's objects were walked ({walked}, {sup} with code support_session)")
check(fingerprint() == before, "guard: nothing of the organisation changed")
# review #4788 (1): the multi-select and the drag, also as a move into the organisation's project
for b_ in ({"ids": [OT], "action": "patch", "data": {"title": "Batch by support"}}, {"ids": [OT], "action": "complete"},
           {"ids": [OT], "action": "delete"}, {"ids": [PT], "action": "patch", "data": {"list_id": OL}},
           {"ids": [PT], "action": "patch_each", "data": {"items": {str(PT): {"list_id": OL}}}}):
    r = Y.post(B + "/api/tasks/batch", json=b_)
    moving = PT in b_["ids"]  # the organisation's task itself is not even seen (count 0); a move into its project is refused
    check(r.ok and r.json().get("count") == 0 and (not moving or bool(r.json().get("errors"))),
          f"support session: batch {b_['action']} changes nothing {r.status_code} {r.text[:150]}")
r = Y.post(B + "/api/tasks/reorder", json={"items": [{"id": OT, "sort": 5}]})
check(r.status_code < 500, f"support session: reorder of the organisation's task {r.status_code} {r.text[:150]}")
r = Y.post(B + "/api/tasks/reorder", json={"items": [{"id": PT, "list_id": OL, "sort": 1}]})
check(refused(r), f"support session: reorder of her private task into the organisation's project 403 support_session {r.status_code} {r.text[:150]}")
check(fingerprint() == before and kt.dbx("SELECT list_id FROM tasks WHERE id=?", (PT,)) == [(PL,)],
      "nothing of the organisation changed, the private task stayed in her private project")
assert Ca.post(B + "/api/support-access", json={"hours": 1, "org_id": CO}).ok
for what, call in WAYS:
    r = call(Y, OT)
    check(r.ok and code(r) != "support_session", f"with the organisation's own support access: {what} {r.status_code} {r.text[:100]}")

print(f"p21254_a: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
