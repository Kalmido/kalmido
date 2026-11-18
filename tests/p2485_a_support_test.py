#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.485.0 (#3939): support access only with the client's consent (hosted). Own container (start.sh, a server key; hosted
with KALMIDO_HOSTED=1, then restarted self-hosted with KEEP=1). Invented accounts only (example.com).
 - without a grant the operator's ways into a client's account / organisation answer 403 (2.399.0, #2687, unchanged)
 - a person grants the own account (1 h to 7 days): the sign-in link and the password link work again; the use is logged on the
   grant (method, route pattern, status, who) and the client sees it; the operator's account list shows until when
 - an organisation admin grants the organisation: the operator renames it; a member cannot grant it (403), sees no grant
 - ending a grant (the person / an admin) or its end time passing closes the door again; a new grant replaces the open one
 - wrong hours = 400; a stranger cannot end somebody else's grant (404); a self-hosted server: hosted=false, POST = 409
freelancer-matrix: own
tenant-matrix: support
usage: p2485_a_support_test.py <datadir>"""
import json
import os
import sys

import kt
from kt import B, check, sess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freelancer_fixture import freelancer, login, org_join  # noqa: E402

KEY = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA="  # a test server key (32 bytes, base64)


def dbw(q, a=()):
    c = kt._dbx.connect(os.path.join(kt.DATA, "tasks.db"))
    try:
        c.execute(q, a)
        c.commit()
    finally:
        c.close()


kt.fresh(env={"KALMIDO_SECRET_KEY": KEY, "KALMIDO_HOSTED": "1"})
A = kt.sess(None)
assert A.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "collab_all": True, "modules": ["comments"]})
A = sess("alice")
uid = {}
for u in ("carl", "cara"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": "password123", "email": f"{u}@example.com"})
    assert r.ok, r.text
    uid[u] = r.json()["id"]
FID, _Fr = freelancer(B, A)
S = {u: login(B, u) for u in ("carl", "cara", "frida")}
for s in S.values():
    assert s.patch(B + "/api/settings", json={"lang": "en", "tour": "done"}).ok
r = S["carl"].post(B + "/api/orgs", json={"name": "Client Studio"})
assert r.status_code == 201, r.text
CO = r.json()["id"]
# 2.635.0 (#5007): since 2.593.0 (#3570) an invitation by e-mail into a company of its own (orgs.self_made) reaches only a
# person its admin may see (else it is dropped): carl and cara are connected first, as colleagues who know each other
dbw("INSERT INTO conn_links(a_id, b_id, created_at) VALUES(?, ?, '2026-01-01T00:00:00Z')", tuple(sorted((uid["carl"], uid["cara"]))))
kt.proved()  # 2.1047.0 (#5007): since 2.1021.0 (#5775) an organisation admin invites by address only an account that proved it
assert S["carl"].put(B + f"/api/orgs/{CO}/members", json={"email": "cara@example.com"}).ok
assert org_join(B, "cara", CO)


def link(who):
    return A.post(B + f"/api/users/{who}/signin-link")


# ---- without a grant (2.399.0, unchanged)
check(link(FID).status_code == 403, "hosted, no grant: no sign-in link for a person without an organisation")
check(A.patch(B + f"/api/admin/orgs/{CO}", json={"name": "Taken over"}).status_code == 403, "hosted, no grant: the client's organisation stays its own")
j = S["frida"].get(B + "/api/support-access").json()
check(j["hosted"] is True and j["account"] is None and j["orgs"] == [] and j["hours"] == [1, 24, 72, 168], f"GET: hosted, nothing open {j}")

# ---- wrong input, wrong person
check(S["frida"].post(B + "/api/support-access", json={"hours": 5}).status_code == 400, "hours outside the list = 400")
check(S["frida"].post(B + "/api/support-access", json={"hours": True}).status_code == 400, "hours true = 400")
check(S["cara"].post(B + "/api/support-access", json={"hours": 1, "org_id": CO}).status_code == 403, "a member cannot grant its organisation")
check(S["frida"].post(B + "/api/support-access", json={"hours": 1, "org_id": CO}).status_code == 403, "a stranger cannot grant somebody's organisation")

# ---- the account grant (a person without an organisation: P4)
r = S["frida"].post(B + "/api/support-access", json={"hours": 1})
check(r.ok and r.json()["grant"]["active"] is True and r.json()["grant"]["org_id"] is None, "frida grants support access for 1 hour " + r.text[:120])
GF = r.json()["grant"]["id"]
r = link(FID)
check(r.ok and r.json().get("link"), "with the grant: the operator makes a sign-in link " + r.text[:120])
TOK = r.json()["link"].split("#signin/")[1]
check(kt.dbx("SELECT COUNT(*) FROM user_invites u, support_grants s WHERE s.id=? AND u.user_id=? AND u.expires_at<=s.ends_at", (GF, FID)) == [(1,)],
      "the link made through the grant ends with it (not after 7 days)")
X = kt.sess(None)
r = X.post(B + "/api/auth/link", json={"token": TOK})
check(r.ok and X.get(B + "/api/state").ok, "the operator signs in as frida with the link " + r.text[:120])
check(kt.dbx("SELECT COUNT(*) FROM sessions t, support_grants s WHERE s.id=? AND t.user_id=? AND t.via='support' AND t.expires_at<=s.ends_at",
             (GF, FID)) == [(1,)], "that session is a support session and ends with the grant at the latest")
for meth, path, body in (("post", "/api/me/tokens", {"name": "ops"}), ("post", "/api/me/app-passwords", {"name": "ops"}),
                         ("post", "/api/me/2fa/totp", {}), ("post", "/api/support-access", {"hours": 168}),
                         ("patch", "/api/me", {"password": "taken-over-1", "current_password": "x"})):
    r = getattr(X, meth)(B + path, json=body)
    check(r.status_code == 403 and r.json().get("code") == "support_session", f"support session: {meth.upper()} {path} -> 403 " + r.text[:100])
check(X.patch(B + "/api/settings", json={"lang": "en"}).ok, "support session: ordinary settings work")
r = A.post(B + f"/api/users/{FID}/invite", json={"send": False})
check(r.ok and "link" not in r.json(), "with the grant: a password link goes to frida's address only, never to the operator " + r.text[:120])
for body in ({"email": "ops@example.com"}, {"password": "taken-over-1"}, {"reset_2fa": True}, {"proxy_login": "ops"}):
    r = A.patch(B + f"/api/users/{FID}", json=body)
    check(r.status_code == 403, f"with the grant: no sign-in data {list(body)} -> 403 " + r.text[:100])
check(kt.dbx("SELECT email FROM users WHERE id=?", (FID,)) == [("frida@example.com",)], "frida's address is unchanged")
# 2.1317.0 (#6496): through support access only lock / unlock and the quota (was: anything but sign-in data, also her name)
r = A.patch(B + f"/api/users/{FID}", json={"display_name": "Frida F"})
check(r.status_code == 403, "with the grant: her display name stays hers " + r.text[:100])
# ---- 2.1317.0 (#6496, audit #4800 F1): a list of what support access changes -- no lasting door for the operator
AL = kt.dbx("SELECT id FROM users WHERE username='alice'")[0][0]
for body in ({"kid": True, "parents": [AL]}, {"kid": True}, {"parents": [AL]}, {"is_admin": True}, {"orgs": []}, {"disabled": False, "kid": True}):
    r = A.patch(B + f"/api/users/{FID}", json=body)
    check(r.status_code == 403, f"with the grant: {list(body)} -> 403 " + r.text[:100])
check(kt.dbx("SELECT kid FROM users WHERE id=?", (FID,))[0][0] in (0, False, None) and not kt.dbx("SELECT 1 FROM kid_parents WHERE kid_id=?", (FID,)),
      "frida stays no kid account, the operator is no parent of hers")
check(A.patch(B + f"/api/users/{FID}", json={"storage_quota_mb": 500}).ok and A.patch(B + f"/api/users/{FID}", json={"disabled": False}).ok,
      "with the grant: the quota and the lock still work")
r = S["frida"].post(B + "/api/my/agents", json={"username": "fridabot"})
check(r.status_code == 201, "frida makes a personal agent " + r.text[:100])
FAG = r.json()["id"]
for body in ({"owner_id": AL}, {"enabled": True, "owner_id": AL}, {"webhook_url": "https://example.com/hook"}, {"scopes": ["read"]},
             {"list_ids": []}, {"display_name": "Ops bot"}):
    r = A.patch(B + f"/api/admin/agents/{FAG}", json=body)
    check(r.status_code == 403, f"with the grant: her agent {list(body)} -> 403 " + r.text[:100])
check(kt.dbx("SELECT owner_id FROM agents WHERE user_id=?", (FAG,)) == [(FID,)], "her agent stays hers")
check(A.patch(B + f"/api/admin/agents/{FAG}", json={"enabled": False}).ok and A.patch(B + f"/api/admin/agents/{FAG}", json={"enabled": True}).ok,
      "with the grant: the kill switch still works")
# #6862: the kill switch is all support access changes on her agent -- no delete, reset, avatar, test event or device
for meth, path in (("post", "/reset"), ("post", "/test"), ("delete", "/machines/999999"), ("delete", "")):
    r = getattr(A, meth)(B + f"/api/admin/agents/{FAG}{path}")
    check(r.status_code == 403, f"with the grant: {meth.upper()} her agent{path} -> 403 " + r.text[:100])
r = A.post(B + f"/api/admin/agents/{FAG}/avatar", files={"file": ("a.png", b"\x89PNG\r\n\x1a\n", "image/png")})
check(r.status_code == 403, "with the grant: no avatar on her agent -> 403 " + r.text[:100])
check(kt.dbx("SELECT 1 FROM agents WHERE user_id=?", (FAG,)) == [(1,)], "her agent still exists")
for path in ("/machines", "/model-usage", "/audit"):
    check(A.get(B + f"/api/admin/agents/{FAG}{path}").ok, f"with the grant: reading her agent{path} still works")
# a kid of the client that lists the operator as a parent (made before, by the client): no sign-in link, no PIN without a grant
r = A.post(B + "/api/users", json={"username": "fkid", "display_name": "Fkid", "password": "password123", "orgs": []})
KID = r.json()["id"]
dbw("UPDATE users SET kid=1, op_made_by=NULL WHERE id=?", (KID,))
dbw("INSERT INTO kid_parents(kid_id, parent_id) VALUES(?, ?)", (KID, FID))
dbw("INSERT INTO kid_parents(kid_id, parent_id) VALUES(?, ?)", (KID, AL))
check(link(KID).status_code == 403, "hosted: the operator as a listed parent of a client's kid makes no sign-in link")
check(A.put(B + f"/api/family/kids/{KID}/pin", json={"pin": "1234"}).status_code == 404, "... and sets no PIN of the kid (family route)")
r = S["frida"].post(B + f"/api/users/{KID}/signin-link")
check(r.ok and r.json().get("link"), "the client herself (a parent) still makes the kid's sign-in link " + r.text[:100])
check(S["frida"].put(B + f"/api/family/kids/{KID}/pin", json={"pin": "1234"}).ok, "... and sets its PIN")
check(link(uid["cara"]).status_code in (403, 404), "frida's grant opens no other account")
users = {u["id"]: u for u in A.get(B + "/api/users?all=1").json()["users"]}
check(not users[FID].get("apart") and users[FID].get("support_until") and users[uid["cara"]].get("apart") is True,
      "the operator's account list: frida open until ..., cara apart")
j = S["frida"].get(B + "/api/support-access").json()
uses = j["account"]["uses"]
check(j["account"]["id"] == GF and any(u["method"] == "POST" and u["route"] == "/api/users/<int:uid>/signin-link" and u["status"] == 200
                                       and u["by"] == "Alice" for u in uses)
      and any(u["route"] == "/api/users/<int:uid>/invite" for u in uses), f"frida sees what the operator did (method, route, who) {uses}")
check(all(set(u) == {"at", "by", "method", "route", "status"} for u in uses), "the log holds no values, only what kind of request")
# 2.503.0 (#4307): what the operator does in the session started with the link is on the client's log too (the session runs as frida)
check(any(u["method"] == "POST" and u["route"] == "/api/auth/link" and u["status"] == 200 and u["by"] == "Support access" for u in uses),
      f"the sign-in with the link is listed, as support access {uses}")
check(any(u["route"] == "/api/state" and u["method"] == "GET" for u in uses), f"a reading in the support session is listed {uses}")
check(any(u["route"] == "/api/me/tokens" and u["status"] == 403 for u in uses), f"a refused write in the support session is listed {uses}")
check(not any(u["route"] == "/api/support-access" and u["method"] == "GET" for u in uses), f"frida's own requests are not listed {uses}")

# 2.1389.0 (#6728, N3): a task the operator writes in the support session is not frida's text (act_by_hand: no support session),
# a task frida writes herself is
r = X.post(B + "/api/tasks", json={"title": "Written by support"})
check(r.status_code in (200, 201) and kt.dbx("SELECT origin FROM tasks WHERE id=?", (r.json().get("id"),))[0][0] is None,
      f"#6728: a task from the support session has no origin 'person' {r.status_code} {r.text[:100]}")
r = S["frida"].post(B + "/api/tasks", json={"title": "Written by frida"})
check(r.status_code in (200, 201) and kt.dbx("SELECT origin FROM tasks WHERE id=?", (r.json().get("id"),))[0][0] == "person",
      f"#6728: frida's own task has it {r.status_code} {r.text[:100]}")


def sup_uses():
    return S["frida"].get(B + "/api/support-access").json()["account"]["uses"]


def sup_n(route):
    return sum(1 for u in sup_uses() if u["route"] == route and u["method"] == "GET")


X.get(B + "/api/state")
X.get(B + "/api/support-access")
X.get(B + "/api/state")
check(sup_n("/api/state") == 1 and sup_n("/api/support-access") == 1, f"the same reading again, also with another in between: one entry {sup_uses()}")
X.get(B + "/api/clients/987654")
X.get(B + "/api/no-such/secret-value")
us = sup_uses()
check(any(u["route"] == "/api/clients/<int:cid>" for u in us) and "987654" not in str(us), f"a route is its pattern, without the id {us}")
check(any(u["route"] == "(unknown)" and u["status"] == 404 for u in us) and "secret-value" not in str(us), f"a path without a route shows no value {us}")
# review: refused requests in a row do not fill the log; a request an early gate refuses (no app header) is listed
X.post(B + "/api/me/tokens", json={"name": "ops"})
X.post(B + "/api/me/tokens", json={"name": "ops"})
check(sum(1 for u in sup_uses() if u["route"] == "/api/me/tokens" and u["status"] == 403) == 1, f"the same refusal again: one entry {sup_uses()}")
X.post(B + "/api/clients", json={"name": "x"}, headers={"X-Requested-With": None})
check(any(u["route"] == "/api/clients" and u["method"] == "POST" and u["status"] == 403 for u in sup_uses()), f"refused by the header check: listed {sup_uses()}")
KEEP = kt.dbx("SELECT uses FROM support_grants WHERE id=?", (GF,))[0][0]
dbw("UPDATE support_grants SET uses=? WHERE id=?", (json.dumps([{"at": "2020-01-01T00:00:00Z", "by": None, "m": "GET", "r": "/old", "s": 200}] * 300), GF))
X.post(B + "/api/me/tokens", json={"name": "ops"})
X.get(B + "/api/state")
n = json.loads(kt.dbx("SELECT uses FROM support_grants WHERE id=?", (GF,))[0][0])
# 2.1350.0 (#6502): the limit of 300 holds for readings only; a write (refused or not) is kept beside them
check(len(n) == 301 and sum(1 for u in n if u["m"] == "GET") == 300 and n[-2]["r"] == "/api/me/tokens" and n[-1]["r"] == "/api/state",
      f"at most 300 readings, the newest stay, the write is kept {len(n)} {n[-2:]}")
dbw("UPDATE support_grants SET uses=? WHERE id=?", (KEEP, GF))
n = len(sup_uses())  # 2.503.0 (#4307): the support session added entries since
A.get(B + "/api/users?all=1")
check(len(S["frida"].get(B + "/api/support-access").json()["account"]["uses"]) == n, "listing the accounts is no use of the grant")

# ---- a new grant replaces the open one; ending closes the door
r = S["frida"].post(B + "/api/support-access", json={"hours": 24})
GF2 = r.json()["grant"]["id"]
check(r.ok and GF2 != GF and kt.dbx("SELECT COUNT(*) FROM support_grants WHERE id=? AND ended_at IS NOT NULL", (GF,)) == [(1,)],
      "a new grant ends the open one")
check(S["carl"].delete(B + f"/api/support-access/{GF2}").status_code == 404, "somebody else cannot end frida's grant")
# 2.1271.0 (#6497): a support session holds only its own grant: replaced, it ends with it (it lived on until then)
check(X.get(B + "/api/state").status_code == 401 and S["frida"].get(B + "/api/state").ok,
      "replaced by a longer grant: the support session of the old one ends, frida's own session stays")
X = kt.sess(None)
r = X.post(B + "/api/auth/link", json={"token": link(FID).json()["link"].split("#signin/")[1]})
check(r.ok and X.get(B + "/api/state").ok, "a new link through the new grant: a support session again " + r.text[:120])
check(S["frida"].delete(B + f"/api/support-access/{GF2}").ok, "frida ends it")
check(X.get(B + "/api/state").status_code == 401 and S["frida"].get(B + "/api/state").ok,
      "ended early: the session started with the operator's link ends too, frida's own session stays")
r = link(FID)
check(r.status_code == 403, "ended: no new sign-in link")
check(link(FID).status_code == 403, "ended: no sign-in link again")
j = S["frida"].get(B + "/api/support-access").json()
check(j["account"] is None and {p["id"] for p in j["past"]} >= {GF, GF2}, "ended grants show as earlier support access")

# ---- the time passing (a real state: the end set into the past)
r = S["frida"].post(B + "/api/support-access", json={"hours": 72})
GF3 = r.json()["grant"]["id"]
check(link(FID).ok, "open again (3 days)")
dbw("UPDATE support_grants SET ends_at='2020-01-01T00:00:00Z' WHERE id=?", (GF3,))
check(link(FID).status_code == 403, "after its end time: closed without anybody ending it")

# ---- 2.1389.0 (#7005 F3): a team agent of the client's organisation -- its work style, data lock, control and rules are not the
# operator's (work-style routes: agents/workstyle.py ws_need_editor): the organisation's rows stay out of the operator's reach
# (tenancy), so the agent is not found, also with the organisation's support grant
r = A.post(B + "/api/admin/agents", json={"username": "studiobot"})
TAG = r.json().get("id") if r.ok else None
check(r.status_code == 201 and TAG, "the operator makes a team agent of its own " + r.text[:100])
dbw("UPDATE agents SET org_id=?, owner_id=NULL WHERE user_id=?", (CO, TAG))  # as if the client's organisation had it (a real state)
WSB = {"quiet_mode": "on"}
CLOSED = (403, 404)
check(A.get(B + f"/api/agents/{TAG}/work-style").status_code in CLOSED, "#7005: no grant: the client's team agent's work style is closed (GET)")
check(A.patch(B + f"/api/agents/{TAG}/work-style", json=WSB).status_code in CLOSED, "#7005: no grant: no change of its work style")
check(A.patch(B + f"/api/agents/{TAG}/data-lock", json={}).status_code in CLOSED, "#7005: no grant: no change of its data lock")
check(A.patch(B + f"/api/agents/{TAG}/control", json={}).status_code in CLOSED, "#7005: no grant: no change of its control")

# ---- #6862 (decision 17.11.2026): a team agent of the client's organisation (made in the database: hosted the operator makes
# none there); its work style, data lock, control and rules are the client's -- without a grant nothing, through it only reading.
# A stranger to the organisation does not even see the agent (row-level security: 404); the operator as a plain member of it
# (no admin) sees it, and there ws_need_editor decides like need_agent_admin (op_foreign_account / op_support_only)
r = A.post(B + "/api/admin/agents", json={"username": "studiobot6862"})
check(r.status_code == 201, "the operator makes a team agent (to move into the client's organisation) " + r.text[:100])
CAG = r.json()["id"]
dbw("UPDATE agents SET owner_id=NULL, org_id=? WHERE user_id=?", (CO, CAG))
WS = {"work_mode": "office"}


def ag_writes(why, codes=(403,)):
    """#6862: no change through ws_need_editor (work style, data lock, control, a rule)."""
    for meth, path, body in (("patch", "/work-style", WS), ("patch", "/data-lock", {"areas": {}}), ("patch", "/control", {"goal": "x"}),
                             ("post", "/rules", {"text": "Ops rule"})):
        r = getattr(A, meth)(B + f"/api/agents/{CAG}{path}", json=body)
        check(r.status_code in codes, f"{why}: {meth.upper()} {path} of the client's team agent -> {codes} " + r.text[:100])


def ops_member(on):
    """The operator as a plain member of the client's organisation (on) or out again."""
    if on:
        dbw("INSERT INTO org_members(org_id, user_id, role) VALUES(?, ?, 'member')", (CO, AL))
    else:
        dbw("DELETE FROM org_members WHERE org_id=? AND user_id=?", (CO, AL))


ag_writes("no grant, a stranger to the organisation", (403, 404))
ops_member(True)
ag_writes("no grant, the operator a plain member")
r = A.get(B + f"/api/agents/{CAG}/work-style")
check(r.status_code == 403, "no grant, a plain member: no reading of its work style either -> 403 " + r.text[:100])
ops_member(False)
# ---- the organisation grant
r = S["carl"].post(B + "/api/support-access", json={"hours": 24, "org_id": CO})
check(r.ok and r.json()["grant"]["org_id"] == CO, "carl (admin) grants the organisation " + r.text[:120])
GO = r.json()["grant"]["id"]
r = A.patch(B + f"/api/admin/orgs/{CO}", json={"name": "Client Studio GmbH"})
check(r.ok and kt.dbx("SELECT name FROM orgs WHERE id=?", (CO,)) == [("Client Studio GmbH",)], "with the grant: the operator renames it " + r.text[:120])
check(link(uid["cara"]).status_code in (403, 404), "the organisation's grant opens no member's account")
WS0 = kt.dbx("SELECT work_style FROM agents WHERE user_id=?", (TAG,))
r = A.patch(B + f"/api/agents/{TAG}/work-style", json=WSB)
check(r.status_code in CLOSED and kt.dbx("SELECT work_style FROM agents WHERE user_id=?", (TAG,)) == WS0,
      "#7005: with the organisation's grant: its work style stays unchanged " + r.text[:100])
r = A.post(B + "/api/users", json={"username": "opsmate", "password": "password123"})
OPS = r.json()["id"]
for body in ({"members_add": [OPS]}, {"admins_add": [OPS]}):
    r = A.patch(B + f"/api/admin/orgs/{CO}", json=body)
    check(r.status_code == 403, f"with the grant: nobody new into the organisation {list(body)} " + r.text[:100])
# 2.1317.0 (#6496): name and symbol only -- no e-mail domain (the operator's registration would join), no member or role change
for body in ({"domains": "ops.example.com"}, {"name": "Client Studio GmbH", "domains": "ops.example.com"}, {"members_remove": [uid["cara"]]},
             {"admins_add": [uid["cara"]]}, {"members_add": []}):
    r = A.patch(B + f"/api/admin/orgs/{CO}", json=body)
    check(r.status_code == 403, f"with the grant: {list(body)} -> 403 " + r.text[:100])
check(kt.dbx("SELECT domains FROM orgs WHERE id=?", (CO,))[0][0] in ("", None), "the organisation's e-mail domains are unchanged")
check(A.patch(B + f"/api/admin/orgs/{CO}", json={"icon": "🎬"}).ok, "with the grant: the operator sets its symbol")
check(not kt.dbx("SELECT 1 FROM org_joins WHERE org_id=? AND user_id=?", (CO, OPS)) and not kt.dbx("SELECT 1 FROM org_members WHERE org_id=? AND user_id=?", (CO, OPS)),
      "... no invitation, no membership")
r = A.post(B + "/api/admin/agents", json={"username": "intruder", "org_id": CO})
check(r.status_code == 403 and not kt.dbx("SELECT 1 FROM users WHERE username='intruder'"), "with the grant: no new agent in the organisation " + r.text[:100])
ops_member(True)
ag_writes("with the grant")
check(A.get(B + f"/api/agents/{CAG}/work-style").ok and A.get(B + f"/api/agents/{CAG}/rules").ok, "with the grant: reading its work style and rules works")
ops_member(False)
check("office" not in json.dumps(kt.dbx("SELECT work_style FROM agents WHERE user_id=?", (CAG,))), "its work style is unchanged")
check(A.patch(B + f"/api/admin/agents/{CAG}", json={"enabled": False}).ok and A.patch(B + f"/api/admin/agents/{CAG}", json={"enabled": True}).ok,
      "with the grant: the kill switch of the client's team agent still works")
r = A.post(B + f"/api/admin/agents/{CAG}/reset")
check(r.status_code == 403, "with the grant: no reset of the client's team agent " + r.text[:100])
j = S["carl"].get(B + "/api/support-access").json()
og = {o["org_id"]: o for o in j["orgs"]}
check(og[CO]["grant"]["id"] == GO and any(u["method"] == "PATCH" for u in og[CO]["grant"]["uses"]), f"carl sees the organisation's grant and its use {og}")
check(S["cara"].get(B + "/api/support-access").json()["orgs"] == [], "a member sees no organisation grant")
check(S["cara"].delete(B + f"/api/support-access/{GO}").status_code == 404, "a member cannot end it")
# the grant holds only while its admin is still an admin
dbw("UPDATE org_members SET role='member' WHERE org_id=? AND user_id=?", (CO, uid["carl"]))
check(A.patch(B + f"/api/admin/orgs/{CO}", json={"name": "Again"}).status_code == 403, "the granting admin demoted: the grant stops")
dbw("UPDATE org_members SET role='admin' WHERE org_id=? AND user_id=?", (CO, uid["carl"]))
check(S["carl"].delete(B + f"/api/support-access/{GO}").ok, "carl ends it")
check(A.patch(B + f"/api/admin/orgs/{CO}", json={"name": "Again"}).status_code == 403, "ended: the organisation is closed again")

# ---- self-hosted: nothing to grant
kt.fresh(env={"KALMIDO_SECRET_KEY": KEY}, keep=True)
F2 = login(B, "frida")
check(F2.get(B + "/api/support-access").json()["hosted"] is False, "self-hosted: hosted=false (the section stays hidden)")
check(F2.post(B + "/api/support-access", json={"hours": 1}).status_code == 409, "self-hosted: no grant (409)")
# 2.1317.0 (#6496): self-hosted the admin keeps the whole account dialog (kid / parents, a parent's sign-in link, the PIN)
A = sess("alice")
r = A.patch(B + f"/api/users/{FID}", json={"kid": True, "parents": [AL]})
check(r.ok and kt.dbx("SELECT 1 FROM kid_parents WHERE kid_id=? AND parent_id=?", (FID, AL)), "self-hosted: the admin makes frida a kid with parents " + r.text[:100])
check(link(KID).ok and A.put(B + f"/api/family/kids/{KID}/pin", json={"pin": "4321"}).ok, "self-hosted: the admin as a parent makes a link and sets the PIN")
sys.exit(kt.done("p2485_a_support"))
