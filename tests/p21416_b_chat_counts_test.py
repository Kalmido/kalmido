#!/usr/bin/env python3
# kalmido-suite:
"""#6400 the room list of the team chat (/api/team, /api/state, a read mark, every push's badge) reads no room whole any more:
the newest main message is one index step per room, a room whose newest id (tchat_room_sig.max_id) is not above my read mark
is not read at all, the @mention test reads the newest TCHAT_MENTION_SCAN unread main messages. Invented names only.
Each case compares /api/team with the statements from before #6400 (DISTINCT ON over all main messages, COUNT + bool_or
over everything after the read mark), run here straight on the database: the same unread count, mention, newest message.
 - a channel with 1,200 messages of another person: no read mark (the whole room), a read mark in the middle, all read
 - the newest main message deleted and an answer in a thread after it: the preview is the main message before
 - a thread I take part in: its unread answers and a mention in it count like before
 - a room without its counter row (rooms from before #4183): counted like before
 - the mention cap: a mention only in an unread message older than the newest 500 unread ones is no longer marked (the
   count stays exact) - red with the old statements, which read every unread message
 - freelancer-matrix: frida without an organisation, her own channel with 700 lines: the same numbers
usage: p21416_b_chat_counts_test.py <datadir>   (a fresh container; P21416B_NOSTART=1 = the server already runs)"""
import os
import sys

import dbx as dbxm
import kt
from freelancer_fixture import freelancer
from kt import B, check, done, sess

FEAT = "collab,comments"
CAP = 500  # TCHAT_MENTION_SCAN of kalmido/collab/teamchat.py
kt.fresh(prefix="P21416B")
kt.docker_logs_on_first_fail()
s0 = sess()
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
uid = {"alice": kt.me_id(A)}


def wdb(sql, args=()):
    c = dbxm.connect(os.path.join(kt.DATA, "tasks.db"))
    try:
        c.execute(sql, args)
        c.commit()
    finally:
        c.close()


ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha"}).json()["id"]
r = A.post(B + "/api/users", json={"orgs": [ORG], "username": "bob", "display_name": "Bob", "password": "password123",
                                   "email": "bob@example.com"})
assert r.ok, r.text
uid["bob"] = r.json()["id"]
Bo = sess("bob")
Bo.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})


def bulk(rid, who, n, body="Note {}"):
    """n main messages of who (None = system lines) straight into the database, one statement."""
    wdb("INSERT INTO tchat_msgs(room_id,user_id,body,created_at) SELECT CAST(? AS BIGINT), CAST(? AS BIGINT), "
        "replace(CAST(? AS TEXT), '{}', g::text), TIMESTAMPTZ '2026-11-01 08:00:00+00' + g * INTERVAL '1 second' "
        "FROM generate_series(1, CAST(? AS INTEGER)) g", (rid, who, body, n))


def before(rid, me):
    """The room as the statements before #6400 saw it: (unread, mention, id of the newest main message)."""
    pat = f"%<@{me}>%"
    last = kt.dbx("SELECT DISTINCT ON (room_id) id FROM tchat_msgs WHERE room_id=? AND deleted_at IS NULL "
                  "AND thread_of IS NULL ORDER BY room_id, id DESC", (rid,))
    u = kt.dbx("""SELECT COUNT(*) FILTER (WHERE COALESCE(m.user_id,0)!=?), COALESCE(bool_or(m.body ILIKE ?), FALSE) FROM tchat_msgs m
                  LEFT JOIN obj_seen d ON d.kind='tchat' AND d.ref_id=m.room_id AND d.user_id=?
                  WHERE m.room_id=? AND m.id>COALESCE(d.seen_id,0) AND m.deleted_at IS NULL AND m.thread_of IS NULL""",
               (me, pat, me, rid))[0]
    t = kt.dbx("""SELECT COUNT(*), COALESCE(SUM(CASE WHEN m.body ILIKE ? THEN 1 ELSE 0 END),0) FROM tchat_msgs m
                  JOIN obj_follow w ON w.kind='tchat_thread' AND w.ref_id=m.thread_of AND w.user_id=? AND w.mode='watch'
                  LEFT JOIN obj_seen t ON t.kind='tchat_thread' AND t.ref_id=m.thread_of AND t.user_id=w.user_id
                  WHERE m.room_id=? AND m.id>COALESCE(t.seen_id,0) AND m.deleted_at IS NULL AND COALESCE(m.user_id,0)!=?""",
               (pat, me, rid, me))[0]
    unread, anym = int(u[0]), bool(u[1])
    return unread + int(t[0]), (bool(unread) and anym) or bool(t[1]), last[0][0] if last else None


def now(S, rid):
    room = next((x for x in S.get(B + "/api/team").json()["rooms"] if x["id"] == rid), None)
    check(room is not None, f"room {rid} in /api/team")
    return room["unread"], room["mention"], (room.get("last") or {}).get("id")


def same(S, me, rid, what):
    got, old = now(S, rid), before(rid, me)
    check(got == old, f"{what}: unread, mention, newest message like before #6400: now {got}, before {old}")
    return got


def read(S, rid, last_id=None):
    r = S.post(B + f"/api/team/rooms/{rid}/read", json={} if last_id is None else {"last_id": last_id})
    check(r.ok, f"read mark {r.status_code} {r.text[:160]}")


# ---------------------------------------------------------------- a channel with 1,200 messages of bob
r = A.post(B + "/api/team/channels", json={"name": "Plans", "org_id": ORG, "members": [uid["bob"]]})
check(r.ok, f"channel {r.status_code} {r.text[:200]}")
CH = r.json()["id"]
bulk(CH, uid["bob"], 1100)
bulk(CH, uid["bob"], 1, body=f"Look here <@{uid['alice']}> please")
bulk(CH, uid["bob"], 99)
u, m, _l = same(A, uid["alice"], CH, "no read mark: the whole room")
check(u >= 1200 and m, f"1,200 unread with the mention among the newest {u} {m}")
mid = kt.dbx("SELECT id FROM tchat_msgs WHERE room_id=? ORDER BY id LIMIT 1 OFFSET 999", (CH,))[0][0]
read(A, CH, mid)
same(A, uid["alice"], CH, "a read mark in the middle")
read(A, CH)
u, m, _l = same(A, uid["alice"], CH, "all read")
check(u == 0 and not m, f"all read: nothing unread {u} {m}")
same(Bo, uid["bob"], CH, "bob, the writer (his own messages are no unread ones)")

# the newest main message deleted, an answer in a thread after it: the preview is the main message before
ids = [x[0] for x in kt.dbx("SELECT id FROM tchat_msgs WHERE room_id=? AND thread_of IS NULL ORDER BY id DESC LIMIT 2", (CH,))]
check(Bo.delete(B + f"/api/team/messages/{ids[0]}").ok, "bob deletes his newest message")
r = A.post(B + f"/api/team/rooms/{CH}/messages", json={"body": "My answer", "thread_of": ids[1]})
check(r.ok, f"alice answers in a thread {r.status_code} {r.text[:160]}")
u, m, last = same(A, uid["alice"], CH, "deleted newest + an answer in a thread")
check(last == ids[1], f"the preview is the newest live main message {last} {ids[1]}")

# a thread alice takes part in: bob's answers, one with a mention
for body in ("First reply", f"Thanks <@{uid['alice']}>"):
    check(Bo.post(B + f"/api/team/rooms/{CH}/messages", json={"body": body, "thread_of": ids[1]}).ok, "bob answers in the thread")
u, m, _l = same(A, uid["alice"], CH, "a thread I take part in")
check(u >= 2 and m, f"the thread's answers count, its mention marks the room {u} {m}")

# a room without its counter row (no change since #4183): counted like before
bulk(CH, uid["bob"], 30)
wdb("DELETE FROM tchat_room_sig WHERE room_id=?", (CH,))
same(A, uid["alice"], CH, "a room without its counter row")

# ---------------------------------------------------------------- the mention cap
r = A.post(B + "/api/team/channels", json={"name": "Long", "org_id": ORG, "members": [uid["bob"]]})
check(r.ok, f"second channel {r.status_code}")
LONG = r.json()["id"]
bulk(LONG, uid["bob"], 5)
read(A, LONG)
bulk(LONG, uid["bob"], 1, body=f"Old call <@{uid['alice']}>")
bulk(LONG, uid["bob"], CAP + 50)
got, old = now(A, LONG), before(LONG, uid["alice"])
check(got[0] == old[0] == CAP + 51 and got[2] == old[2], f"behind the cap: the same count and newest message {got} {old}")
check(old[1] and not got[1], f"a mention older than the newest {CAP} unread messages is not marked (cap #6400) {got} {old}")
bulk(LONG, uid["bob"], 1, body=f"New call <@{uid['alice']}>")
same(A, uid["alice"], LONG, "a new mention inside the cap")

# ---------------------------------------------------------------- freelancer-matrix: frida, no organisation
FID, Fr = freelancer(B, A, "frida", features=FEAT)
r = Fr.post(B + "/api/team/channels", json={"name": "Own notes"})
check(r.ok, f"frida's own channel {r.status_code} {r.text[:200]}")
FC = r.json()["id"]
bulk(FC, None, 700, body="System line {}")
same(Fr, FID, FC, "frida: no read mark")
read(Fr, FC)
same(Fr, FID, FC, "frida: all read")
sys.exit(done("p21416_b_chat_counts"))
