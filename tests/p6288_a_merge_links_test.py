#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1426.0 (#6288, audit #4742 D2): merging clients and contacts keeps the links of the core (obj_links) and undo brings them back.
obj_links has no foreign key: the trigger kalmido_olnk_gone deletes the links of a row deleted for good, so before a merge
deleted the merged records their links were gone (clients: all of them, contacts: those with the contact as target).
core/merges.py mg_olnk_move now moves both directions; Undo (mg_undo_refs) puts them back.
 - clients: a task linked to client B, B linked to a task, a task linked to A and B (falls together), A linked to B (a link
   to itself: goes), a live link to B against one in the trash at A (the live one wins); the overview counts the links;
   A + B merged -> every link hangs on A; Undo -> each one back on B as it was, the dropped ones too
 - contacts: B as the source of a task link (rel contact) and as the target of a task's link; merged into A -> both at A;
   Undo -> both back at B
 - every delete trigger *_gone on clients / contacts is named in core/merges.py MG_GONE, and both merges call its function
usage: p6288_a_merge_links_test.py <datadir>"""
import ast
import os
import re
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
from freelancer_fixture import FEATURES  # noqa: E402
from kt import B, DATA, H, check, docker_logs_on_first_fail, done, fresh, sess  # noqa: E402

ROOT = os.path.dirname(N)


def sql(q, args=(), write=False):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(q, args)
        if write:
            c.commit()
            return None
        return r.fetchall()
    finally:
        c.close()


def row(lid):
    """(src_kind, src_id, dst_kind, dst_id, in the trash) of a link, None when gone."""
    r = sql("SELECT src_kind, src_id, dst_kind, dst_id, deleted_at IS NOT NULL FROM obj_links WHERE id=?", (lid,))
    return tuple(r[0]) if r else None


def link(s, kind, rid, okind, oid):
    r = s.post(B + f"/api/obj/{kind}/{rid}/links", json={"kind": okind, "id": oid})
    check(r.status_code in (200, 201) and r.json().get("id"), f"setup: link {kind} {rid} -> {okind} {oid} " + r.text[:200])
    return r.json().get("id")


fresh(prefix="P6288A")
docker_logs_on_first_fail()
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Example Studio", "lang": "en", "collab_all": True, "modules": ["cal", "comments", "collab"]})
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEATURES})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
ALICE = A.get(B + "/api/state").json()["me"]["id"]

# ================================================================ the trigger list (source + database)
src = open(os.path.join(ROOT, "kalmido/core/merges.py"), encoding="utf-8").read()
m = re.search(r"^MG_GONE = (\{[^}]*\})", src, re.M)
gone = ast.literal_eval(m.group(1)) if m else {}
trig = sql("SELECT DISTINCT p.proname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_proc p ON p.oid=t.tgfoid "
           "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal AND n.nspname=current_schema() "
           "AND c.relname IN ('clients', 'contacts') AND right(p.proname, 5) = '_gone'")
names = sorted(r[0] for r in trig)
check("kalmido_olnk_gone" in names, f"the database has the links' delete trigger on clients / contacts {names}")
check(names and all(x in gone for x in names), f"every *_gone trigger on clients / contacts is named in MG_GONE {names} {gone}")
for f in ("kalmido/contacts/merge.py", "kalmido/team/clientmerge.py"):
    code = open(os.path.join(ROOT, f), encoding="utf-8").read()
    check(all(re.search(rf"\b{h}\(", code) for h in set(gone.values())), f"{f} calls every function of MG_GONE {sorted(set(gone.values()))}")

# ================================================================ clients
r = A.post(B + "/api/lists", json={"name": "Shoot", "org_id": ORG})
check(r.ok, "setup: a project " + r.text[:160])
P = r.json()["id"]
TK1, TK2, TK3 = (A.post(B + "/api/tasks", json={"title": t, "list_id": P}).json()["id"] for t in ("Brief", "Offer", "Invoice"))
CA, CB = (A.post(B + "/api/clients", json={"name": n, "org_id": ORG}).json().get("id") for n in ("Acme Ltd", "ACME Ltd (old)"))
check(CA and CB, f"setup: two clients {CA} {CB}")
L1 = link(A, "task", TK1, "client", CB)      # B as the target
L2 = link(A, "client", CB, "task", TK2)      # B as the source
L3 = link(A, "task", TK2, "client", CA)      # the same task at A ...
L4 = link(A, "task", TK2, "client", CB)      # ... and at B: falls together
L5 = link(A, "client", CA, "client", CB)     # A to B: a link to itself after the merge
L6 = link(A, "task", TK3, "client", CA)      # in the trash at A ...
L7 = link(A, "task", TK3, "client", CB)      # ... live at B: the live one wins
check(A.delete(B + f"/api/obj/links/{L6}").ok and row(L6)[4], "setup: the link of task 3 at A into the trash")

r = A.post(B + "/api/clients/merge", json={"target": CA, "ids": [CA, CB], "dry": True})
check(r.ok and (r.json().get("counts") or {}).get("obj_links") == 5, "the overview counts the five links of B " + r.text[:300])
check(row(L1) == ("task", TK1, "client", CB, False), "the overview changes nothing")
r = A.post(B + "/api/clients/merge", json={"target": CA, "ids": [CA, CB]})
check(r.ok and r.json().get("run_id"), "A and B merged " + r.text[:200])
RID = r.json().get("run_id")
check(row(L1) == ("task", TK1, "client", CA, False), f"the task's link to B hangs on A (rückfall #6288: deleted with B) {row(L1)}")
check(row(L2) == ("client", CA, "task", TK2, False), f"B's link to a task leaves from A {row(L2)}")
check(row(L3) == ("task", TK2, "client", CA, False) and row(L4) is None, f"the double fell together {row(L3)} {row(L4)}")
check(row(L5) is None, "the link between A and B is gone (A to itself)")
check(row(L7) == ("task", TK3, "client", CA, False) and row(L6) is None, f"the live link wins over the one in the trash {row(L7)} {row(L6)}")
lk = A.get(B + f"/api/obj/client/{CA}/links").json().get("links") or []
check(sorted((x["dir"], x["other"]["id"]) for x in lk) == sorted([("in", TK1), ("out", TK2), ("in", TK2), ("in", TK3)]),
      f"A lists all of them {[(x['dir'], x['other']['id']) for x in lk]}")

r = A.post(B + f"/api/clients/merges/{RID}/undo")
check(r.ok, "the merge undone " + r.text[:200])
check(row(L1) == ("task", TK1, "client", CB, False), f"undo: the task's link back at B {row(L1)}")
check(row(L2) == ("client", CB, "task", TK2, False), f"undo: B's link to a task back {row(L2)}")
check(row(L3) == ("task", TK2, "client", CA, False) and row(L4) == ("task", TK2, "client", CB, False),
      f"undo: the double is two links again {row(L3)} {row(L4)}")
check(row(L5) == ("client", CA, "client", CB, False), f"undo: the link between A and B is back {row(L5)}")
check(row(L7) == ("task", TK3, "client", CB, False) and row(L6) == ("task", TK3, "client", CA, True),
      f"undo: the live link back at B, the one at A back in the trash {row(L7)} {row(L6)}")
lk = A.get(B + f"/api/obj/client/{CB}/links").json().get("links") or []
check(sorted((x["dir"], x["other"]["id"]) for x in lk if x["other"]["kind"] == "task") == sorted([("in", TK1), ("out", TK2), ("in", TK2), ("in", TK3)]),
      f"B lists its task links again {[(x['dir'], x['other']['id']) for x in lk]}")

# ================================================================ contacts
BK = A.post(B + "/api/books", json={"name": "Private book"}).json()["id"]
C1, C2 = (A.post(B + "/api/contacts", json={"book_id": BK, "fn": n}).json()["id"] for n in ("Kim Example", "Kim Example (old)"))
AP = A.post(B + "/api/lists", json={"name": "Alice private", "org_id": None}).json()["id"]
AT1, AT2 = (A.post(B + "/api/tasks", json={"title": t, "list_id": AP}).json()["id"] for t in ("Call Kim", "Send Kim the plan"))
r = A.post(B + f"/api/tasks/{AT1}/contacts", json={"contact_id": C2, "kind": "waiting"})
check(r.ok, "setup: the contact as the source (rel contact) " + r.text[:200])
K1 = sql("SELECT id FROM obj_links WHERE src_kind='contact' AND src_id=? AND dst_id=?", (C2, AT1))[0][0]
sql("INSERT INTO obj_links(org_id, src_kind, src_id, dst_kind, dst_id, rel, created_by) VALUES(NULL, 'task', ?, 'contact', ?, 'related', ?)",
    (AT2, C2, ALICE), write=True)
K2 = sql("SELECT id FROM obj_links WHERE src_kind='task' AND src_id=? AND dst_kind='contact'", (AT2,))[0][0]
r = A.post(B + "/api/contacts/merge", json={"target": C1, "ids": [C2]})
check(r.ok and r.json().get("run_id"), "the contacts merged " + r.text[:200])
CR = r.json().get("run_id")
check(row(K1) == ("contact", C1, "task", AT1, False), f"the contact's task link leaves from A {row(K1)}")
check(row(K2) == ("task", AT2, "contact", C1, False), f"the task's link to the contact hangs on A (rückfall #6288: deleted with B) {row(K2)}")
r = A.post(B + f"/api/contacts/merges/{CR}/undo")
check(r.ok, "the contact merge undone " + r.text[:200])
check(row(K1) == ("contact", C2, "task", AT1, False) and row(K2) == ("task", AT2, "contact", C2, False),
      f"undo: both links back at B {row(K1)} {row(K2)}")

sys.exit(done("p6288_a_merge_links"))
