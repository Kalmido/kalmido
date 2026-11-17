#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1321.0 (#6397): every reader of the shared search index obj_search narrows to its own rows over an index first (the
visible projects / books / calendars / rooms on node_id, the row-level security's organisations on org_ref, the own agent
chats on owner_id), then tests the words and ranks; names=True is two arms instead of "tsv @@ q OR names LIKE" (the OR made
the GIN index useless). Audit #4765: a person of an almost empty organisation paid for the rows of a large one.
Mode workspaces: Alpha (alice + bob, a few rows), Beta (carol, thousands of tasks, comments and contacts with the same
words), a person without an organisation (frida). Invented names only.
freelancer-matrix: search (frida finds her own task and contact by a word and by a part of a name, nobody else's)
 - the hits stay the same: a word start, umlauts either way (Müller / Mueller), a part of a ticket key and of a contact's name
   or phone number (the second arm), notes, the comment search; Beta's rows with the same words are never found by Alpha
 - the two arms give exactly the rows of the old OR condition (tasks, contacts, bookmarks; several words, umlauts, digits)
 - the plans of the real requests (each statement on obj_search explained on the request's own connection, under the
   policy): no Seq Scan on obj_search, and every scan of it goes through a scope index (node_id, org_ref, owner_id, the
   names rows or the primary key from the source row) -- never the word index alone over every organisation
usage: p6397_a_search_scope_test.py <datadir>"""
import json
import subprocess
from urllib.parse import quote

import kt
from kt import B, CT, check, dbx, sess
from freelancer_fixture import FEATURES, freelancer

FEAT = FEATURES
N_BIG = 6000

kt.fresh()
A = kt.setup()
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
A.post(B + "/api/admin/orgs", json={"name": "Kalmido"})
ids = {}
for u in ("bob", "carol"):
    r = A.post(B + "/api/users", json={"orgs": [1], "username": u, "display_name": u.title(), "password": "password123", "email": f"{u}@example.com"})
    assert r.ok, r.text
    ids[u] = r.json()["id"]
kt.fresh(env={"KALMIDO_INSTANCE_MODE": "workspaces"}, keep=True)
A, Bo, Ca = sess("alice"), sess("bob"), sess("carol")
for s in (A, Bo, Ca):
    s.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALPHA = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": ids["carol"]})
assert r.status_code == 201, r.text
BETA = r.json()["id"]
check(A.delete(B + f"/api/orgs/{ALPHA}/members/{ids['carol']}").ok, "setup: carol leaves Alpha")


def made(r, what):
    check(r.status_code in (200, 201), f"setup: {what} ({r.status_code} {r.text[:160]})")
    j = r.json() if r.ok else {}
    return j.get("id") or (j.get("contact") or j.get("bookmark") or j.get("note") or {}).get("id")


# ---- Alpha: a few rows
LA = made(A.post(B + "/api/lists", json={"name": "Alpha list", "org_id": ALPHA}), "Alpha's list")
check(A.put(B + f"/api/lists/{LA}/members", json={"user_id": ids["bob"], "role": "edit"}).ok, "setup: the Alpha list shared with bob")
T1 = made(A.post(B + "/api/tasks", json={"title": "Rechnung Müller", "list_id": LA}), "task 1")
T2 = made(A.post(B + "/api/tasks", json={"title": "Paket", "content": "Angebot fuer Kunde Mueller", "list_id": LA}), "task 2")
T3 = made(A.post(B + "/api/tasks", json={"title": "Ticket", "list_id": LA}), "task 3")
T5 = made(A.post(B + "/api/tasks", json={"title": "Nothing here", "list_id": LA}), "task 5")
dbx("UPDATE lists SET ticket_key='KUNDO' WHERE id=?", (LA,))  # after the tasks: only T3 gets a number
dbx("UPDATE tasks SET ticket_no=47 WHERE id=?", (T3,))  # names = "kundo-47" (a part of the ticket key: the second arm)
check(A.post(B + f"/api/tasks/{T5}/comments", json={"body": "Die Rechnung ist raus"}).ok, "setup: Alpha's comment")
CA = made(A.post(B + "/api/contacts", json={"fn": "Erika Müller", "phones": [{"type": "cell", "value": "+49 171 5550123"}]}), "alice's contact")
NA = made(A.post(B + f"/api/lists/{LA}/notes", json={"title": "Protokoll", "body": "Rhabarberkuchen für alle"}), "Alpha's note")
BA = made(A.post(B + "/api/bookmarks", json={"url": "https://kuchenwerkstatt.example/rezepte", "title": "Rezepte",
                                              "note": "Pflaumenkuchen"}), "alice's bookmark")

# ---- Beta: the same words, thousands of times
LB = made(Ca.post(B + "/api/lists", json={"name": "Beta list", "org_id": BETA}), "Beta's list")
TB = made(Ca.post(B + "/api/tasks", json={"title": "Rechnung Müller Beta", "content": "Angebot Kunde", "list_id": LB}), "Beta's task")
check(Ca.post(B + f"/api/tasks/{TB}/comments", json={"body": "Rechnung Beta"}).ok, "setup: Beta's comment")
CB = made(Ca.post(B + "/api/contacts", json={"fn": "Erika Müller Beta", "phones": [{"type": "cell", "value": "+49 171 5550999"}]}), "carol's contact")
check(dbx("SELECT org_id FROM contacts WHERE id=?", (CB,))[0][0] == BETA, "setup: carol's contact carries Beta")
dbx("INSERT INTO tasks(list_id, title, content, created_at, updated_at) SELECT ?, 'Rechnung Müller Beta ' || g, 'Angebot Kunde Mueller', "
    "created_at, updated_at FROM tasks, generate_series(1, ?) g WHERE tasks.id=?", (LB, N_BIG, TB))
dbx("INSERT INTO obj_comments(kind, ref_id, user_id, body, created_at) SELECT 'task', t.id, c.user_id, 'Rechnung Beta ' || t.id, c.created_at "
    "FROM obj_comments c, tasks t WHERE c.kind='task' AND c.ref_id=? AND t.list_id=? AND t.id<>?", (TB, LB, TB))
cols = [r[0] for r in dbx("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='contacts' "
                          "AND column_name NOT IN ('id', 'fn', 'uid', 'href') ORDER BY ordinal_position")]
dbx(f"INSERT INTO contacts(fn, uid, href, {', '.join(cols)}) SELECT 'Erika Müller Beta ' || g, 'p6397-' || g, 'p6397-' || g || '.vcf', "
    f"{', '.join('x.' + c for c in cols)} FROM contacts x, generate_series(1, ?) g WHERE x.id=?", (N_BIG, CB))
for t in ("tasks", "obj_comments", "contacts", "obj_search"):
    dbx(f"ANALYZE {t}")
n_beta = dbx("SELECT COUNT(*) FROM obj_search WHERE org_ref=?", (BETA,))[0][0]
check(n_beta > 3 * N_BIG, f"setup: Beta's rows are in the shared index ({n_beta})")
check(dbx("SELECT COUNT(*) FROM obj_comments WHERE kind='task' AND org_id=?", (BETA,))[0][0] > N_BIG,
      "setup: Beta's comments carry Beta (row-level security, org_ref)")

# ---- a person without an organisation
FID, Fr = freelancer(B, A, "frida")
FT = made(Fr.post(B + "/api/tasks", json={"title": "Rechnung Frida"}), "frida's task")
FC = made(Fr.post(B + "/api/contacts", json={"fn": "Rahmenbauer Nord"}), "frida's contact")


def tasks(s, q):
    r = s.get(B + "/api/tasks", params={"scope": "search", "q": q})
    return {t["id"] for t in r.json().get("tasks", [])} if r.ok else {"error", r.status_code}


def contacts(s, q):
    r = s.get(B + "/api/contacts", params={"q": q})
    return {x["id"] for x in r.json().get("items", [])} if r.ok else {"error", r.status_code}


def palette(s, q):
    r = s.get(B + "/api/search", params={"q": q, "limit": 20})
    j = r.json() if r.ok else {}
    return {h["task"]["id"] for h in j.get("hits", [])}, j


# ---- the hits
check(tasks(Bo, "müller") == {T1, T2}, f"bob: a word start, umlaut in the title and 'ue' in the notes, not Beta's ({tasks(Bo, 'müller')})")
check(tasks(Bo, "MUELLER") == {T1, T2}, "bob: 'Mueller' finds both the same")
check(tasks(Bo, "ndo-4") == {T3}, f"bob: a part of the ticket key (the names arm) ({tasks(Bo, 'ndo-4')})")
check(tasks(Bo, "angebot kunde") == {T2}, "bob: two words, both required")
got = tasks(Ca, "müller")  # a page of Beta's thousands
check(got and not got & {T1, T2} and all(r[0] == LB for r in dbx("SELECT list_id FROM tasks WHERE id = ANY(CAST(? AS BIGINT[]))", ("{" + ",".join(str(x) for x in got) + "}",))),
      f"carol finds only Beta's tasks ({len(got)})")
check(tasks(Fr, "rechnung") == {FT}, f"frida finds her own task, nobody else's ({tasks(Fr, 'rechnung')})")
hits, j = palette(Bo, "rechnung")
check(hits == {T1, T5}, f"bob's palette: the title and the comment, not Beta's ({hits})")
check(any(h.get("where") == "comment" and h["task"]["id"] == T5 for h in j.get("hits", [])), "bob's palette: the comment hit says 'comment'")
check(contacts(A, "ülle") == {CA}, f"alice: a part of the name with the umlaut, not Beta's ({contacts(A, 'ülle')})")
check(contacts(A, "uelle") == {CA}, "alice: the part as 'ue' the same")
check(contacts(A, "5550") == {CA}, "alice: a part of the phone number")
check(contacts(A, "erika") == {CA}, "alice: a word start")
check(CB in contacts(Ca, "ülle") and CA not in contacts(Ca, "ülle"), "carol finds only Beta's contacts")
check(contacts(Fr, "bauer") == {FC}, f"frida: a part of her contact's name ({contacts(Fr, 'bauer')})")
check(contacts(Fr, "erika") == set(), "frida: nobody else's contact")
check({n["id"] for n in A.get(B + "/api/notes", params={"q": "rhabarber"}).json().get("notes", [])} == {NA}, "alice: the note's text")
check(BA in {x["id"] for x in A.get(B + "/api/bookmarks", params={"q": "pflaumen"}).json().get("items", [])}, "alice: the bookmark's note")
r = Bo.get(B + "/api/search", params={"kind": "messages", "q": "rechnung"})
mt = {h.get("task_id") for h in (r.json().get("items") or r.json().get("hits") or [])} if r.ok else {"error"}
check(T5 in mt and TB not in mt, f"bob's message search: Alpha's comment, not Beta's ({sorted(x for x in mt if x)[:5]})")

# ---- the two arms are the old OR condition (system context: every row)
EQ = '''
import json
from kalmido.core.db import connect
from kalmido.core.objsearch import osr_cond, osr_ids_sql
c = connect()
out = []
for kind, q in %r:
    cond, a = osr_cond(q, "s", names=True)
    old = sorted(r[0] for r in c.execute(f"SELECT s.ref_id FROM obj_search s WHERE s.kind='{kind}' AND {cond}", a).fetchall())
    ids, b = osr_ids_sql(kind, q, names=True)
    new = sorted(r[0] for r in c.execute(f"SELECT s.ref_id FROM obj_search s WHERE s.kind='{kind}' AND s.ref_id IN {ids}", b).fetchall())
    out.append([kind, q, len(old), old == new])
c.close()
print(json.dumps(out))
'''
CASES = [("task", "müller"), ("task", "mueller beta 12"), ("task", "ndo-4"), ("task", "kundo-47"), ("task", "rechnung frida"),
         ("contact", "ülle"), ("contact", "erika mül"), ("contact", "5550"), ("contact", "bauer nord"), ("contact", "mueller beta 59"),
         ("bookmark", "werkstatt"), ("bookmark", "pflaumen")]
r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0", CT, "python", "-c", "import app\n" + EQ % (CASES,)],
                   capture_output=True, text=True)
try:
    eq = json.loads(r.stdout.strip().splitlines()[-1])
except (ValueError, IndexError):
    eq = []
check(len(eq) == len(CASES), f"the arm comparison ran {r.stderr[-600:]}")
for kind, q, n, same in eq:
    print(f"info: {kind} '{q}': {n} rows", flush=True)
    check(same, f"#6397: the two arms give the rows of the OR condition ({kind} '{q}', {n} rows)")
check(any(n > N_BIG for _k, _q, n, _s in eq) and any(0 < n < 5 for _k, _q, n, _s in eq), "the comparison has many and few rows")

# ---- the plans of the real requests (every statement on obj_search explained on the request's own connection)
PROBE = '''
from kalmido.core import pg
from kalmido.core.config import app as fa
P = []
_ex = pg.Conn.execute
def ex(self, sql, args=None):
    if "obj_search " in sql and not sql.startswith("EXPLAIN"):
        v = _ex(self, "EXPLAIN (FORMAT JSON) " + sql, args).fetchone()[0]
        P.append([sql[:160], json.loads(v) if isinstance(v, str) else v])
    return _ex(self, sql, args)
pg.Conn.execute = ex
cl = fa.test_client()
H = {"X-Requested-With": "kalmido"}
cl.post("/api/auth/login", json={"username": %r, "password": "password123"}, headers=H, base_url="https://localhost")
r = cl.get(%r, headers=H, base_url="https://localhost")
pg.Conn.execute = _ex
print(json.dumps({"status": r.status_code, "plans": P}))
'''
# ix5278_obj_search_parent: the comments of objects other than tasks (pkind = the few registered kinds, core/objsearch.py
# osr_comment_hits) -- narrower than the organisation while those kinds have few comments; the org condition stays in the query
SCOPE_IX = {"ix5278_obj_search_node", "ix6397_obj_search_org", "ix6397_obj_search_owner", "ix6397_obj_search_names", "obj_search_pkey",
            "ix5278_obj_search_parent"}


def probe(user, path):
    r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0", CT, "python", "-c",
                        "import app, json\n" + PROBE % (user, path)], capture_output=True, text=True)
    out = r.stdout.strip().splitlines()
    try:
        return json.loads(out[-1]) if out else {"err": r.stderr[-800:]}
    except ValueError:
        return {"err": out[-1][:300] + " " + r.stderr[-800:]}


def scans(plan):
    """[(node type, index names of the scan and its bitmap children)] of every scan of obj_search in the plan."""
    out = []

    def idx(n):
        s = {n["Index Name"]} if n.get("Index Name") else set()
        for k in n.get("Plans", []):
            if k.get("Node Type", "").startswith("Bitmap") or k.get("Node Type") in ("BitmapAnd", "BitmapOr"):
                s |= idx(k)
        return s

    def walk(n):
        if n.get("Relation Name") == "obj_search":
            out.append((n["Node Type"], idx(n)))
        for k in n.get("Plans", []):
            walk(k)
    walk(plan[0]["Plan"])
    return out


REQS = [("bob", "/api/tasks?scope=search&q=" + quote("müller")), ("bob", "/api/tasks?scope=search&q=ndo-4"),
        ("bob", "/api/search?q=rechnung"), ("bob", "/api/search?kind=messages&q=rechnung"),
        ("alice", "/api/contacts?q=" + quote("ülle")), ("alice", "/api/notes?q=rhabarber"), ("alice", "/api/bookmarks?q=pflaumen"),
        ("frida", "/api/tasks?scope=search&q=rechnung"), ("frida", "/api/contacts?q=bauer"), ("frida", "/api/search?q=rechnung")]
for who, path in REQS:
    res = probe(who, path)
    plans = res.get("plans") or []
    check(res.get("status") == 200 and plans, f"{who} {path}: the request ran and its statements on obj_search were explained {str(res)[:300]}")
    for sql, p in plans:
        sc = scans(p)
        print(f"info: {who} {path}: {sql[:90]!r} -> {sc}", flush=True)
        check(sc, f"#6397 {who} {path}: the plan reads obj_search ({sql[:80]!r})")
        check(not [t for t, _i in sc if t == "Seq Scan"], f"#6397 {who} {path}: no Seq Scan on obj_search {sc}")
        check(all(i & SCOPE_IX for _t, i in sc), f"#6397 {who} {path}: every scan of obj_search goes through a scope index first {sc}")

raise SystemExit(kt.done("p6397_a_search_scope"))
