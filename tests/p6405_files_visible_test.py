#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6405 API tests: the file store's "what may this account see" (files/store.py fs_visible_sql_c) starts over indexed arms
and looks at the trash upward from the tops of the set only; a folder's listing reads the roles of all its rows at once,
its path (crumbs) only the chain upward, the trash its chains and roles at once; ?limit pages a folder's children.
Own container (kt.fresh). Invented people and names only.
tenant-matrix: files  freelancer-matrix: files
 - the same set: for every person (organisation admin, a member, a member through a group share, the admin of another
   organisation, an agent, a person without an organisation) the new subquery gives exactly the ids of the one before
   2.1459 (a frozen copy below) -- own nodes, an "everyone in the organisation" folder, shares (person, group, expired),
   another organisation, a person without an organisation, deleted nodes and nodes below a deleted folder one and three
   levels up (a share inside a folder in the trash)
 - what that set holds: bob sees the shared folder in a closed folder, never the one inside a deleted folder; eve nothing of Alpha
 - the plan: with sequential scans off, the new subquery reads fs_nodes through indexes only (EXPLAIN)
 - a folder's listing: the statements of GET /api/files?parent for a member without ownership stay the same (at most +2)
   for 30 more children (was a chain and a share query per row); the same items and roles as before
 - ?limit=10: ten children, folders first, more=true; limit 100: all of them, more=false; without limit all, more=false
 - crumbs: bob in a subfolder of the folder shared with him sees the path from that folder down, not the closed folder above it
 - trash: alice's trash lists the deleted tops only (not what lies inside a deleted folder), roles owner; its statements
   stay the same (at most +2) for 12 more entries
usage: p6405_files_visible_test.py <datadir>"""
import base64
import json
import os
import re
import subprocess
import sys

import kt
from kt import B, CT, check, sess
from freelancer_fixture import freelancer, org_join

KEY = base64.b64encode(os.urandom(32)).decode()
kt.fresh(env={"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_TEST_TIMING_ALL": "1", "KALMIDO_SECRET_KEY": KEY}, prefix="P6405")
kt.docker_logs_on_first_fail()
FEAT = "cal,comments,collab,files"
TIMING = re.compile(r'db;dur=[\d.]+;desc="n=(\d+)"')
TS = "2026-10-01T10:00:00Z"


def nstmt(r):
    m = TIMING.search(r.headers.get("Server-Timing", ""))
    return int(m.group(1)) if m else -1


def in_app(code):
    """Python inside the server container (the app loaded, c = a connection, system context) -> stdout + stderr."""
    body = "\n".join("    " + x for x in code.split("\n"))
    out = subprocess.run(["docker", "exec", CT, "python", "-c",
                          "import app\nfrom kalmido.core.db import connect\nfrom kalmido.core.pg import system_ctx\nc = connect()\n"
                          "with system_ctx(c):\n" + body + "\nc.close()"], capture_output=True, text=True)
    return out.stdout + out.stderr


def last_json(out):
    for line in reversed(out.strip().splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                break
    return {"_err": out[-2000:]}


def node(name, owner, org=None, parent=None, kind="folder", access="", deleted=False, agent=None):
    return kt.dbx("INSERT INTO fs_nodes(parent_id, kind, name, owner_id, org_id, agent_id, org_access, created_by, created_at, updated_at, deleted_at) "
                  "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                  (parent, kind, name, owner, org, agent, access, owner, TS, TS, TS if deleted else None))[0]["id"]


def share(nid, by, user=None, group=None, agent=None, role="view", expires=None):
    kt.dbx("INSERT INTO fs_shares(node_id, user_id, group_id, agent_id, role, expires_at, created_by, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
           (nid, user, group, agent, role, expires, by, TS))


# ---------------------------------------------------------------- setup: two organisations, members, an agent, a freelancer
A = kt.setup()
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True, "modules": ["comments"]})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
U = {}
for u in ("bob", "carl", "eve"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": "password123",
                                       "email": f"{u}@example.com", "orgs": [] if u == "eve" else [{"id": ORG, "role": "member"}]})
    assert r.ok, r.text
    U[u] = r.json()["id"]
    if u != "eve":
        check(org_join(B, u, ORG), f"setup: {u} is a member of Alpha")
ORG2 = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": U["eve"]}).json()["id"]
Bo, Ca, Ev = sess("bob"), sess("carl"), sess("eve")
for s, ws in ((Bo, ORG), (Ca, ORG), (Ev, ORG2)):
    s.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done", "workspace": f"org:{ws}"})
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})
r = A.post(B + "/api/my/agents", json={"username": "filebot", "display_name": "File Bot", "scopes": ["read", "files:read"], "org_id": ORG})
check(r.ok, "setup: alice's agent " + r.text[:200])
AG = r.json().get("id")
FID, Fr = freelancer(B, A, "fiona", features=FEAT)
GRP = kt.dbx("INSERT INTO groups(name, created_at) VALUES('Crew', ?) RETURNING id", (TS,))[0]["id"]
kt.dbx("INSERT INTO group_members(group_id, user_id, added_at) VALUES(?, ?, ?)", (GRP, U["carl"], TS))
BOB, CARL, EVE = U["bob"], U["carl"], U["eve"]

# ---------------------------------------------------------------- the tree
T = node("Team", ALICE, ORG, access="view")  # everyone in Alpha reads it
T1 = node("t1.txt", ALICE, ORG, T, "file")
T2 = node("Plans", ALICE, ORG, T)
T2a = node("plan.txt", ALICE, ORG, T2, "file")
T3 = node("t3-gone.txt", ALICE, ORG, T, "file", deleted=True)
C = node("Closed", ALICE, ORG)
C1 = node("Shared with bob", ALICE, ORG, C)
C1a = node("c1a.txt", ALICE, ORG, C1, "file")
C1b = node("Sub", ALICE, ORG, C1)
C2 = node("Trashed", ALICE, ORG, C, deleted=True)
C2a = node("Shared inside the trash", ALICE, ORG, C2)
C2a1 = node("c2a1.txt", ALICE, ORG, C2a, "file")
C3 = node("crew.txt", ALICE, ORG, C, "file")
C4 = node("expired.txt", ALICE, ORG, C, "file")
BF = node("Bob's", BOB, ORG)
BF1 = node("b1.txt", BOB, ORG, BF, "file")
D1 = node("D1", ALICE, ORG, deleted=True)
D2 = node("D2", ALICE, ORG, D1)
D3 = node("D3", ALICE, ORG, D2)
D4 = node("D4 shared", ALICE, ORG, D3)
D5 = node("d5.txt", ALICE, ORG, D4, "file")
P = node("Private", ALICE)
P1 = node("p1.txt", ALICE, None, P, "file")
P2 = node("P2 gone", ALICE, None, P, deleted=True)
P2a = node("p2a.txt", ALICE, None, P2, "file")
F = node("Fiona's", FID)
F1 = node("f1.txt", FID, None, F, "file")
E = node("Beta", EVE, ORG2)
E1 = node("e1.txt", EVE, ORG2, E, "file")
AGN = node("Bot notes", ALICE, ORG, agent=AG)
share(C1, ALICE, user=BOB)
share(C2a, ALICE, user=BOB)
share(D4, ALICE, user=BOB, role="edit")
share(C3, ALICE, group=GRP)
share(C4, ALICE, user=BOB, expires="2020-01-01T00:00:00Z")
share(F, FID, user=BOB)
share(E, EVE, user=BOB)  # another organisation: the boundary keeps it out
share(T2, ALICE, agent=AG)
BIG = node("Big", ALICE, ORG, access="edit")
BIG2 = node("Big two", ALICE, ORG, access="edit")


def kids(parent, n, folders):
    kt.dbx("INSERT INTO fs_nodes(parent_id, kind, name, owner_id, org_id, created_by, created_at, updated_at) "
           "SELECT ?, CASE WHEN g <= ? THEN 'folder' ELSE 'file' END, 'item ' || lpad(g::text, 3, '0'), ?, ?, ?, ?, ? "
           "FROM generate_series(1, ?) g", (parent, folders, ALICE, ORG, ALICE, TS, TS, n))


kids(BIG, 30, 5)
kids(BIG2, 60, 5)
PEOPLE = {"alice": ALICE, "bob": BOB, "carl": CARL, "eve": EVE, "agent": AG, "fiona": FID}

# ---------------------------------------------------------------- the same set as the subquery before #6405
OLD = r'''
def old_visible_sql(c, uid):
    """fs_visible_sql with the connection (reads the account's organisations / groups once)."""
    uid = int(uid)
    ctx = acx_of(c, uid)
    agent = ctx.role == "agent"
    now = _now().replace("'", "")
    roots = []  # 2.1340.0 (#6613): the documents folders of the organisations where uid is accounting
    if agent:
        orgs = f"n.org_id IS NULL OR n.org_id = {int(ctx.agent_org_id)}" if ctx.agent_org_id else "n.org_id IS NULL"
        seed = (f"n.agent_id = {uid} OR n.id IN (SELECT node_id FROM fs_shares WHERE (agent_id = {uid} OR user_id = {uid}) "
                f"AND (expires_at IS NULL OR expires_at > '{now}') AND COALESCE(list_own, 0)=0)")  # 2.568.0 (#4739, review F6)
    else:
        oids = ",".join(str(int(x)) for x in ctx.org_ids) or "0"
        orgs = f"n.org_id IS NULL OR n.org_id IN ({oids})"
        admin = [int(o) for o in ctx.org_ids if is_org_admin(c, uid, o)]
        seed = f"n.owner_id = {uid}"
        lim = [int(o) for o in ctx.org_ids if org_role_key(c, uid, o) in ("guest", "accounting", "readonly")]
        oa = _fs_open_area_sql(lim)  # 2.200.0 A (#2747, review 4): a demoted admin's ownership of an open area's tree gives nothing
        if oa:
            seed = f"(n.owner_id = {uid} AND n.id NOT IN {oa})"
        if admin:
            seed += f" OR n.org_id IN ({','.join(map(str, admin))})"
        # 2.143.0 A (#2151): "everyone in the organisation" folders only for member / admin / read-only; accounting: the
        # organisation's documents folder; guests: their own nodes and shares
        rks = {int(o): org_role_key(c, uid, o) for o in ctx.org_ids}
        full = ",".join(str(o) for o, rk in rks.items() if rk not in ("guest", "accounting")) or "0"
        seed += f" OR (n.org_access IN ('view', 'edit') AND n.org_id IN ({full}))"
        acc = [o for o, rk in rks.items() if rk == "accounting"]
        roots = [int(x) for x in (_fs_docs_root(c, o) for o in acc) if x]
        if roots:  # 2.1340.0 (#6613): the receipts below the documents folder, not its whole tree (fs_role's rule)
            seed += (f" OR n.id IN (SELECT r.node_id FROM rc_receipts r WHERE r.org_id IN ({','.join(map(str, acc))}) AND "
                     f"r.node_id IN (WITH RECURSIVE dr(id) AS (SELECT id FROM fs_nodes WHERE id IN ({','.join(map(str, roots))}) "
                     f"UNION SELECT x.id FROM fs_nodes x JOIN dr ON x.parent_id = dr.id) SELECT id FROM dr))")
        if collab_all():
            seed += (f" OR n.id IN (SELECT node_id FROM fs_shares WHERE (user_id = {uid} OR group_id IN "
                     f"(SELECT group_id FROM group_members WHERE user_id = {uid})) AND (expires_at IS NULL OR expires_at > '{now}') "
                     f"AND COALESCE(list_own, 0)=0)")  # 2.568.0 (#4739, review F6): not "Shared with me" through a project's own row
    # 2.1045.0 (#5823): an excluded knowledge folder is listed only when it (or a node below it) is shared itself; 2.1225.0
    # (#5862): for people too (the exclusions of a whole knowledge area shared with them)
    step = dl_wiki_step_sql(c, uid)
    # #6613: the accounting role's documents folder itself is listed, without descending into it (fv would);
    # #6953 (reader job/5148 F3): so are the folders between it and a receipt of the organisation (fs_role's rule)
    rl = ",".join(map(str, roots))
    root_u = (f" UNION SELECT id FROM fs_nodes WHERE id IN ({rl})"
              f" UNION SELECT id FROM fs_nodes WHERE kind = 'folder' AND id IN (WITH RECURSIVE ra(id, pid) AS ("
              f"SELECT n.id, n.parent_id FROM fs_nodes n JOIN rc_receipts r ON r.node_id = n.id WHERE r.org_id IN ({','.join(map(str, acc))}) AND {live_sql('n')} "
              f"UNION SELECT p.id, p.parent_id FROM fs_nodes p JOIN ra ON p.id = ra.pid WHERE ra.id NOT IN ({rl})) "
              f"SELECT id FROM ra WHERE id IN (WITH RECURSIVE dr(id) AS (SELECT id FROM fs_nodes WHERE id IN ({rl}) "
              f"UNION SELECT x.id FROM fs_nodes x JOIN dr ON x.parent_id = dr.id) SELECT id FROM dr))") if roots else ""
    return (f"(WITH RECURSIVE fv(id) AS (SELECT n.id FROM fs_nodes n WHERE ({seed}) AND ({orgs}) "
            f"UNION SELECT n.id FROM fs_nodes n JOIN fv ON n.parent_id = fv.id WHERE ({orgs}){step}), "
            f"fd(id) AS (SELECT id FROM fs_nodes WHERE deleted_at IS NOT NULL "
            f"UNION SELECT n.id FROM fs_nodes n JOIN fd ON n.parent_id = fd.id), "
            f"fr(id) AS (SELECT id FROM fv{root_u}) "
            f"SELECT id FROM fr WHERE id NOT IN (SELECT id FROM fd){_mail_hidden(c, uid)}{_receipts_hidden_sql(c, uid, ctx.org_ids)}"  # 2.187.1 A (#2735): agents too
            f"{_ref_hidden(c, uid)}{_lock_hidden(c, agent)}{_for_sql(c, uid)})")

'''
CODE = f"""
import json
from flask import g
from kalmido.core.config import app as fa
from kalmido.files.store import *  # noqa: F403
from kalmido.files.store import (_now, _fs_open_area_sql, _fs_docs_root, _mail_hidden, _receipts_hidden_sql, _ref_hidden,
                                 _lock_hidden, _for_sql)
{OLD}
out = {{}}
for name, uid in {PEOPLE!r}.items():
    with fa.test_request_context("/api/files"):
        old = sorted(r[0] for r in c.execute(f"SELECT id FROM fs_nodes WHERE id IN {{old_visible_sql(c, uid)}}"))
    with fa.test_request_context("/api/files"):
        sql = fs_visible_sql_c(c, uid)
        new = sorted(r[0] for r in c.execute(f"SELECT id FROM fs_nodes WHERE id IN {{sql}}"))
        c.execute("SET LOCAL enable_seqscan = off")
        plan = "\\n".join(r[0] for r in c.execute(f"EXPLAIN SELECT id FROM fs_nodes WHERE id IN {{sql}}"))
        c.execute("SET LOCAL enable_seqscan = on")
    out[name] = {{"old": old, "new": new, "plan": plan}}
print(json.dumps(out))
"""
res = last_json(in_app(CODE))
check("_err" not in res, f"in the app: the old and the new subquery ran {res.get('_err')}")
SEQ = re.compile(r"Seq Scan on fs_nodes (n|t|a|b|d|r0|s0)\b")
for name, x in res.items():
    if name == "_err":
        continue
    check(x["old"] == x["new"], f"{name}: the same visible set as before {sorted(set(x['old']) ^ set(x['new']))}")
    bad = [ln for ln in x["plan"].split("\n") if SEQ.search(ln)]
    check(not bad, f"{name}: the subquery reads fs_nodes through indexes (sequential scans off) {bad}")
if "bob" in res:
    bo, ev, ag = set(res["bob"]["new"]), set(res["eve"]["new"]), set(res["agent"]["new"])
    check({T, T1, T2, T2a, C1, C1a, C1b, BF, BF1, F, F1, BIG, BIG2} <= bo, f"bob: Team, the folder shared with him, his own, Fiona's share {sorted(bo)}")
    check(not bo & {T3, C, C2, C2a, C2a1, C3, C4, D2, D3, D4, D5, E, E1, P, P1}, "bob: nothing deleted, nothing below a deleted folder "
          f"(one and three levels up), no expired share, nothing of Beta, nothing private {sorted(bo & {T3, C, C2, C2a, C2a1, C3, C4, D2, D3, D4, D5, E, E1, P, P1})}")
    check(C3 in set(res["carl"]["new"]) and C4 not in set(res["carl"]["new"]), "carl: the file shared with his group")
    check(not ev & {T, C, C1, BF, P, F, BIG}, "eve: nothing of Alpha, nothing private of others")
    check({E, E1} <= ev, "eve: her own organisation")
    check({AGN, T2, T2a} <= ag and not ag & {T, C1, P}, f"agent: its own node and the share, nothing else {sorted(ag)}")
    al = set(res["alice"]["new"])
    check({P, P1, C, C1, C3} <= al and not al & {P2, P2a, D1, D4, C2, T3}, "alice: her trees without the trash")


# ---------------------------------------------------------------- a folder's listing: statements, paging, crumbs
def listing(s, nid, q=""):
    r = s.get(B + f"/api/files?parent={nid}{q}")
    return r, (r.json() if r.ok else {})


r1, j1 = listing(Bo, BIG)
r2, j2 = listing(Bo, BIG2)
check(r1.ok and len(j1.get("items", [])) == 30 and j1.get("more") is False, f"bob lists Big: 30 children {r1.status_code}")
check(len(j2.get("items", [])) == 60, "bob lists Big two: 60 children")
check(all(x.get("role") == "edit" for x in j1.get("items", [])), f"bob: role edit on every child (the folder's access) {[x.get('role') for x in j1.get('items', [])][:5]}")
n1, n2 = nstmt(r1), nstmt(r2)
check(n1 > 0 and n2 - n1 <= 2, f"a folder's listing: statements stay the same for 30 more children ({n1} -> {n2})")
print(f"PERF folder listing as a member: 30 children {n1} statements, 60 children {n2}", flush=True)
rp, jp = listing(Bo, BIG2, "&limit=10")
it = jp.get("items", [])
check(rp.ok and len(it) == 10 and jp.get("more") is True, f"limit=10: ten children, more=true {len(it)} {jp.get('more')}")
check([x["kind"] for x in it[:5]] == ["folder"] * 5 and it[5]["name"] == "item 006", f"limit=10: folders first, then by name {[x['name'] for x in it]}")
rp, jp = listing(Bo, BIG2, "&limit=100")
check(len(jp.get("items", [])) == 60 and jp.get("more") is False, "limit=100: all 60, more=false")
rc, jc = listing(Bo, C1b)
check(rc.ok and [x["id"] for x in jc.get("crumbs", [])] == [C1, C1b], f"crumbs: from the folder shared with bob down {jc.get('crumbs')}")
rc, jc = listing(A, C1b)
check([x["id"] for x in jc.get("crumbs", [])] == [C, C1, C1b], f"crumbs: alice from her top {jc.get('crumbs')}")
rc, _jc = listing(Bo, C2a)
check(rc.status_code == 404, f"bob: the shared folder inside the trash does not open {rc.status_code}")

rf, jf = listing(Fr, F, "&limit=50")
check(rf.ok and [x["id"] for x in jf.get("items", [])] == [F1] and jf.get("more") is False, f"fiona (no organisation): her folder pages too {rf.status_code}")
check([x["id"] for x in jf.get("crumbs", [])] == [F], f"fiona: her crumbs {jf.get('crumbs')}")
rf, jf = listing(Bo, F)
check(rf.ok and [x["id"] for x in jf.get("items", [])] == [F1], "bob: fiona's folder shared with him")

# ---------------------------------------------------------------- trash
rt = A.get(B + "/api/files?space=trash")
ids = {x["id"] for x in rt.json().get("items", [])} if rt.ok else set()
check({T3, C2, D1, P2} <= ids and not ids & {C2a, C2a1, D2, P2a}, f"trash: the deleted tops, not what lies inside them {sorted(ids)}")
check(all(x.get("role") == "owner" for x in rt.json().get("items", [])), "trash: alice owns every entry")
for k in range(12):
    node(f"gone {k}.txt", ALICE, None, P, "file", deleted=True)
rt2 = A.get(B + "/api/files?space=trash")
check(len(rt2.json().get("items", [])) == len(ids) + 12, "trash: 12 more entries")
check(nstmt(rt2) - nstmt(rt) <= 2, f"trash: statements stay the same for 12 more entries ({nstmt(rt)} -> {nstmt(rt2)})")
print(f"PERF trash: {len(ids)} entries {nstmt(rt)} statements, {len(ids) + 12} entries {nstmt(rt2)}", flush=True)
sys.exit(kt.done("p6405_files_visible"))
