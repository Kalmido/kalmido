#!/usr/bin/env python3
# kalmido-suite:
"""2.1364.0 part C (#6297, audit #4741): the security hardening round, points 1-7, one section each. One container
(start.sh, mode workspaces); invented names only (example.com).
 1 an organisation invitation ends with its admin's right (demoted: the rows go; a right lost on a way without the hook:
   accepting is refused, OJN_BY); audit #4818 (b) an instance admin adding the invited person directly and removing her
   again leaves no invitation to come back by; (c) a demotion of an admin waits for the organisation's row (FOR UPDATE)
 2 a text that only starts like a sealed value ("kenc1:...") is sealed like any other (the ledger entry of a person without
   an organisation reads, changes and deletes again; freelancer-matrix: office); a real sealed value is kept
 3 restoring a deleted task comment / team chat message: the author does not undo a project admin's delete; not in a frozen
   DM; not as a read-only person of the organisation (each was 200 before)
 4 a mail reply through the own address token of a read-only member with a colleague's forged From: no comment, a note
 5 another person's own ticket types: only the ones their private project I see offers, without note template, switched off
   ones or id (was: every own type of that person)
 6 a table shared by e-mail address tells nothing of an account behind it: the file store's node shows neither the bound
   account's share nor a history line naming it, and its share id answers 404 like an unknown one (was 400); Fable review
   job/5254 F2: the same person shared by name in the file store's dialog gets no second, hidden row -- the address opens
   again and the one share goes on by name, as in the table's own dialog
 7 the organisation's table / knowledge trash: a writing member deletes for good only what she made, one at a time (was:
   any one, one at a time; Fable review job/5254 F3: put into the trash by her is not enough); its admin any
usage: p21364_c_haertung_test.py <datadir>"""
import base64
import os
import subprocess
import sys
import threading

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
import testclock  # noqa: E402
import dbx as dbxm  # noqa: E402
from freelancer_fixture import FEATURES, freelancer, org_join  # noqa: E402
from kt import B, CT, DATA, check, dbx, sess, until  # noqa: E402

kt.fresh(env={"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ORGCRYPT_DELAY": "0",
              "KALMIDO_SECRET_KEY": base64.b64encode(os.urandom(32)).decode()}, prefix="P21364C")
A = kt.setup()
ids = {}
for u in ("bob", "carl", "dora", "erna", "gerda"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": kt.PASSWORD, "email": f"{u}@example.com"})
    assert r.ok, r.text
    ids[u] = r.json()["id"]
BOB, CARL, DORA, ERNA, GERDA = (ids[u] for u in ("bob", "carl", "dora", "erna", "gerda"))
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": BOB})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
dbx("DELETE FROM org_members WHERE org_id=? AND user_id<>?", (ORG, BOB))
kt.proved()  # an organisation admin invites by address only an account that proved it
Bo = sess("bob")


def joins(user):
    return [j["org_id"] for j in sess(user).get(B + "/api/orgs").json().get("joins", [])]


def invite(s, email, role="member"):
    return s.put(B + f"/api/orgs/{ORG}/members", json={"email": email, "role": role}).ok


# ==== 1: an invitation ends with its admin's right
check(invite(Bo, "carl@example.com", "admin") and org_join(B, "carl", ORG), "(1) setup: carl joins Alpha as admin")
Ca = sess("carl")
check(invite(Ca, "dora@example.com") and ORG in joins("dora"), "(1) carl (admin) invites dora: her invitation is open")
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": CARL, "role": "member"}).ok, "(1) bob demotes carl to member")
check(ORG not in joins("dora") and sess("dora").post(B + f"/api/orgs/{ORG}/join").status_code == 404,
      "(1) carl's invitation of dora ended with his admin right (not listed, accepting 404)")
check(dbx("SELECT COUNT(*) FROM org_joins WHERE org_id=? AND created_by=?", (ORG, CARL))[0][0] == 0, "(1) carl's invitation rows went")
# a right that ends on a way without the hook (a row changed by hand): accepting checks the inviter itself (OJN_BY)
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": CARL, "role": "admin"}).ok and invite(Ca, "erna@example.com"),
      "(1) carl is admin again and invites erna")
dbx("UPDATE org_members SET role='member' WHERE org_id=? AND user_id=?", (ORG, CARL))
check(ORG not in joins("erna") and sess("erna").post(B + f"/api/orgs/{ORG}/join").status_code == 404,
      "(1) carl no admin (row changed directly): erna's invitation is not open, accepting 404")
dbx("UPDATE org_members SET role='admin' WHERE org_id=? AND user_id=?", (ORG, CARL))
check(org_join(B, "erna", ORG), "(1) carl admin again: erna accepts (only the inviter's right closed it)")
check([r[0] for r in dbx("SELECT role FROM org_members WHERE org_id=? AND user_id=?", (ORG, ERNA))] == ["member"], "(1) erna is a member")

# (b) audit #4818: the instance admin adds the invited person directly and removes her: no invitation is left to return by
check(invite(Bo, "gerda@example.com", "admin") and ORG in joins("gerda"), "(1b) bob invites gerda as admin")
check(A.patch(B + f"/api/admin/orgs/{ORG}", json={"members_add": [GERDA]}).ok, "(1b) the instance admin adds gerda directly")
check(dbx("SELECT COUNT(*) FROM org_joins WHERE org_id=? AND user_id=?", (ORG, GERDA))[0][0] == 0, "(1b) her invitation row went with the adding")
check(A.patch(B + f"/api/admin/orgs/{ORG}", json={"members_remove": [GERDA]}).ok, "(1b) the instance admin removes gerda")
check(sess("gerda").post(B + f"/api/orgs/{ORG}/join").status_code == 404 and not dbx(
      "SELECT 1 FROM org_members WHERE org_id=? AND user_id=?", (ORG, GERDA)), "(1b) gerda cannot come back as admin by the old invitation")
# org_leave: a row left beside a membership (an older server) goes when the person leaves
dbx("INSERT INTO org_joins(org_id,user_id,role,created_by,created_at) VALUES(?,?,'admin',?,now())", (ORG, ERNA, BOB))
check(sess("erna").delete(B + f"/api/orgs/{ORG}/members/{ERNA}").ok, "(1b) erna leaves Alpha")
check(dbx("SELECT COUNT(*) FROM org_joins WHERE org_id=? AND user_id=?", (ORG, ERNA))[0][0] == 0
      and sess("erna").post(B + f"/api/orgs/{ORG}/join").status_code == 404, "(1b) leaving took her invitation row along (no way back)")

# (c) audit #4818: a demotion of an admin locks the organisation's row before counting the admins
dbc, dbn = dbxm._target(DATA)
hold = subprocess.Popen(["docker", "exec", "-i", dbc, "psql", "-U", "kalmido", "-d", dbn, "-X", "-q", "-A", "-t"], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
hold.stdin.write(f"BEGIN;\nSELECT id FROM orgs WHERE id={int(ORG)} FOR UPDATE;\n\\echo held\n")
hold.stdin.flush()
check(until(lambda: hold.stdout.readline().strip() == "held", 30), "(1c) a second session holds Alpha's row")
res = {}
t = threading.Thread(target=lambda: res.update(r=sess("carl").put(B + f"/api/orgs/{ORG}/members", json={"user_id": CARL, "role": "member"})))
t.start()


def waiting():
    return dbx("SELECT 1 FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%FROM orgs WHERE id=% FOR UPDATE%' "
               "AND query NOT LIKE '%pg_stat_activity%'") or ("r" in res)


check(until(waiting, 30) and "r" not in res, "(1c) carl stepping down waits for the organisation's row (no count without it)")
hold.stdin.write("COMMIT;\n")
hold.stdin.close()
hold.wait(30)
t.join(60)
check("r" in res and res["r"].ok, f"(1c) after the other session ends, the demotion goes through ({res.get('r') and res['r'].status_code})")
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": BOB, "role": "member"}).status_code == 409,
      "(1c) bob, now the only admin, cannot step down (counted after the lock)")


def py_in_app(code):
    """Python inside the app container, one transaction (system context)."""
    r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "TASKS_WATCHDOG=0", CT, "python", "-c",
                        "import app\nfrom kalmido.core.db import connect\nfrom kalmido.core.pg import system_ctx\nc = connect()\n"
                        "with system_ctx(c):\n" + "".join("    " + x + "\n" for x in code.splitlines()) + "c.commit()\nc.close()"],
                       capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


# ==== 2: a text that only looks sealed
FAKE = "kenc1:AAAA"
FID, Fr = freelancer(B, A, "frida")
Fr.patch(B + "/api/settings", json={"features": "cal,comments,collab,office,clients,docs"})
check(Fr.put(B + "/api/office/settings", json={"lang": "de", "currency": "EUR", "company_fields": {"name": "Frida Beispiel"}}).ok, "(2) setup: frida's office")
check(Fr.put(B + "/api/office/books/ledger/settings", json={"method": "balance", "size": "small"}).ok, "(2) setup: balance sheet")
DAY = testclock.today().isoformat()
r = Fr.post(B + "/api/office/books/ledger/entries", json={"day": DAY, "debit": "6825", "credit": "3070", "amount": "5.00", "text": FAKE})
check(r.status_code == 201, f"(2) an entry with the text {FAKE} {r.status_code} {r.text[:120]}")
E = r.json() if r.ok else {}
raw = dbx("SELECT text FROM office_ledger_entries WHERE id=?", (E.get("id", 0),))
check(raw and raw[0][0] != FAKE, f"(2) not stored as it came (sealed like any text): {raw and raw[0][0][:20]}")
r = Fr.get(B + f"/api/office/books/ledger?year={DAY[:4]}")
mine = [e for e in (r.json().get("entries") or []) if e.get("id") == E.get("id")] if r.ok else []
check(r.ok and mine and mine[0].get("text", "").lstrip("\u200b") == FAKE, f"(2) the year reads (was 500) and shows the text {r.status_code}")
r = Fr.put(B + f"/api/office/books/ledger/entries/{E.get('id')}", json={"text": FAKE + "B", "expect_updated_at": E.get("updated_at")})
check(r.ok, f"(2) the entry can be changed {r.status_code}")
check(Fr.delete(B + f"/api/office/books/ledger/entries/{E.get('id')}").ok, "(2) and deleted")
out = py_in_app(f"from kalmido.core import orgcrypt as oc\nv = oc.oc_enc(c, {ORG}, 't.c', 'geheim')\n"
                f"print('KEEP', oc.oc_enc(c, {ORG}, 't.c', v) == v, oc.oc_dec(c, {ORG}, 't.c', oc.oc_enc(c, {ORG}, 't.c', '{FAKE}')).lstrip(chr(8203)) == '{FAKE}',"
                f" oc.oc_enc(c, {ORG}, 't.d', v) != v)")
check("KEEP True True True" in out, f"(2) a real sealed value is kept, a fake one sealed, one of another place sealed anew: {out[-300:]}")

# ==== 3: restoring a comment / a team chat message
Bo, Ca = sess("bob"), sess("carl")
for s_ in (Bo, Ca):
    s_.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG}"})
L = Bo.post(B + "/api/lists", json={"name": "Hardening", "org_id": ORG}).json().get("id")
check(L and Bo.put(B + f"/api/lists/{L}/members", json={"user_id": CARL, "role": "edit"}).ok, "(3) setup: bob's project, carl edits")
T = Bo.post(B + "/api/tasks", json={"list_id": L, "title": "Check"}).json().get("id")
Bo.get(B + "/api/team")
ROOM = next((x["id"] for x in Ca.get(B + "/api/team").json().get("rooms", []) if x.get("list_id") == L), None)
check(T and ROOM, f"(3) setup: a task and the project's channel {T} {ROOM}")


def comment(s, text):
    return s.post(B + f"/api/tasks/{T}/comments", json={"body": text}).json().get("id")


def say(s, rid, text):
    return s.post(B + f"/api/team/rooms/{rid}/messages", json={"body": text}).json().get("id")


C1, M1 = comment(Ca, "Carl's note"), say(Ca, ROOM, "Carl's message")
check(Bo.delete(B + f"/api/comments/{C1}").ok and Bo.delete(B + f"/api/team/messages/{M1}").ok, "(3) bob (project admin) takes both down")
check(Ca.post(B + f"/api/comments/{C1}/restore").status_code == 403, "(3) carl does not bring back his comment bob deleted (403)")
check(Ca.post(B + f"/api/team/messages/{M1}/restore").status_code == 403, "(3) nor his message bob deleted (403)")
check(Bo.post(B + f"/api/comments/{C1}/restore").ok and Bo.post(B + f"/api/team/messages/{M1}/restore").ok, "(3) bob may undo his own delete")
C0, M0 = comment(Ca, "Own note"), say(Ca, ROOM, "Own message")
check(Ca.delete(B + f"/api/comments/{C0}").ok and Ca.post(B + f"/api/comments/{C0}/restore").ok
      and Ca.delete(B + f"/api/team/messages/{M0}").ok and Ca.post(B + f"/api/team/messages/{M0}/restore").ok,
      "(3) carl still restores what he deleted himself")
# a frozen DM: the partner is locked
r = A.post(B + "/api/users", json={"username": "hanna", "display_name": "Hanna", "password": kt.PASSWORD, "email": "hanna@example.com"})
HANNA = r.json()["id"]
A.patch(B + f"/api/admin/orgs/{ORG}", json={"members_add": [HANNA]})
Bo.put(B + f"/api/lists/{L}/members", json={"user_id": HANNA, "role": "view"})  # carl works with her (a common project)
DM = Ca.post(B + "/api/team/dm", json={"user_id": HANNA}).json().get("id")
M2 = say(Ca, DM, "Before the lock")
check(DM and M2 and Ca.delete(B + f"/api/team/messages/{M2}").ok, "(3) carl deletes his DM message to hanna")
dbx("UPDATE users SET disabled=? WHERE id=?", (True, HANNA))  # hanna's account is locked: the DM is frozen
check(Ca.post(B + f"/api/team/messages/{M2}/restore").status_code == 403, "(3) nothing comes back into a frozen DM (403)")
# a read-only person of the organisation
C3, M3 = comment(Ca, "Later read-only"), say(Ca, ROOM, "Later read-only")
check(Ca.delete(B + f"/api/comments/{C3}").ok and Ca.delete(B + f"/api/team/messages/{M3}").ok, "(3) carl deletes his own comment and message")
check(Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": CARL, "role": "readonly"}).ok, "(3) carl becomes read-only in Alpha")
check(Ca.post(B + f"/api/comments/{C3}/restore").status_code == 403, "(3) read-only: the comment does not come back (403)")
check(Ca.post(B + f"/api/team/messages/{M3}/restore").status_code == 403, "(3) read-only: the message does not come back (403)")

# ==== 4: a mail reply of a read-only member with a forged From (carl is read-only in Alpha since section 3)
dbx("INSERT INTO task_mail(task_id,msg_id,sender,kind,created_at) VALUES(?,?,'',?,now())", (T, "<t6297@example.com>", "out"))
n0 = dbx("SELECT COUNT(*) FROM obj_comments WHERE kind='task' AND ref_id=?", (T,))[0][0]
MAIL = "From: Bob <bob@example.com>\nTo: carl+tok@example.com\nSubject: Re: Check\nIn-Reply-To: <t6297@example.com>\nMessage-ID: <f6297@example.com>\n\nForged"
out = py_in_app("import email\nfrom kalmido.integrations.taskmail import tmr_take\n"
                f"print('TAKE', tmr_take(c, email.message_from_string({MAIL!r}), None, {CARL}, 'token')[0])")
check("TAKE note" in out, f"(4) carl's token with bob's address as From: a note, no comment ({out[-200:]})")
check(dbx("SELECT COUNT(*) FROM obj_comments WHERE kind='task' AND ref_id=?", (T,))[0][0] == n0, "(4) no comment on the task")
out = py_in_app("import email\nfrom kalmido.integrations.taskmail import tmr_take\n"
                f"print('TAKE', tmr_take(c, email.message_from_string({MAIL!r}), None, {BOB}, 'token')[0])")
check("TAKE comment" in out, f"(4) bob's own token: still a comment ({out[-200:]})")

# ==== 5: another person's own ticket types
TT = {}
for name, on in (("Offered", True), ("Unpicked", True), ("Switched off", False)):
    r = Bo.post(B + "/api/ticket-types", json={"space": "private", "name": name, "template": f"secret {name}", "enabled": on})
    check(r.status_code in (200, 201), f"(5) setup: bob's own type {name} {r.text[:120]}")
    TT[name] = r.json().get("key")
P = Bo.post(B + "/api/lists", json={"name": "Bob private", "org_id": None}).json().get("id")
check(Bo.patch(B + f"/api/lists/{P}", json={"ttypes": ["bug", TT["Offered"], TT["Switched off"]]}).ok, "(5) setup: the project offers one of the own types")
r = Bo.put(B + f"/api/lists/{P}/members", json={"user_id": CARL, "role": "view"})
check(r.ok, f"(5) setup: carl sees bob's private project {r.text[:120]}")
seen = [x for x in Ca.get(B + "/api/ticket-types").json().get("types", []) if x.get("owner_id") == BOB]
check([x["key"] for x in seen] == [TT["Offered"]], f"(5) carl meets only the type the project offers ({[x.get('name') for x in seen]})")
check(seen and "template" not in seen[0] and "id" not in seen[0] and seen[0].get("enabled") is True,
      f"(5) without note template and id ({sorted(seen[0]) if seen else None})")
own = [x for x in Bo.get(B + "/api/ticket-types").json().get("types", []) if x.get("owner_id") == BOB]
check(len(own) == 3 and all("template" in x for x in own), "(5) bob still sees all his own types with templates")

# ==== 6: sharing a table by address
Bo.patch(B + "/api/settings", json={"workspace": "private"})
SH = Bo.post(B + "/api/sheets", json={"title": "Prices", "space": "private"}).json().get("id")
r1 = Bo.post(B + f"/api/sheets/{SH}/shares", json={"email": "dora@example.com", "role": "read"})
r2 = Bo.post(B + f"/api/sheets/{SH}/shares", json={"email": "nobody6297@example.com", "role": "read"})
check(SH and r1.status_code == r2.status_code == 201 and sorted(r1.json()) == sorted(r2.json()), "(6) the same answer with and without an account")
FSS = dbx("SELECT s.id FROM fs_shares s JOIN fs_nodes n ON n.id=s.node_id WHERE n.ref_kind='sheet' AND n.ref_id=? AND s.user_id=?", (SH, DORA))
check(bool(FSS), "(6) setup: dora's account holds the table through the address (bound)")
NODE = dbx("SELECT id FROM fs_nodes WHERE kind='ref' AND ref_kind='sheet' AND ref_id=?", (SH,))[0][0]
nd = Bo.get(B + f"/api/files/nodes/{NODE}").json()
check(not any(x.get("user_id") == DORA for x in nd.get("shares", [])), f"(6) the file store's node lists no share of dora ({nd.get('shares')})")
check(not any(f"user:{DORA}" in (x.get("detail") or "") or x.get("user_id") == DORA for x in nd.get("log", [])),
      "(6) and its history names no account of an address")
fid = FSS[0][0] if FSS else 0
codes = (Bo.patch(B + f"/api/sheets/{SH}/shares/{fid}", json={}).status_code, Bo.patch(B + f"/api/sheets/{SH}/shares/{fid + 9999}", json={}).status_code)
check(codes == (404, 404), f"(6) the bound share's id answers like an unknown one {codes}")
check(Bo.get(B + f"/api/sheets/{SH}/shares").ok, "(6) the table's own dialog still lists its shares")

# ==== 7: the trash of an organisation's tables and knowledge pages
r = A.post(B + "/api/users", json={"username": "ida", "display_name": "Ida", "password": kt.PASSWORD, "email": "ida@example.com"})
IDA = r.json()["id"]
check(A.patch(B + f"/api/admin/orgs/{ORG}", json={"members_add": [IDA]}).ok, "(7) setup: ida is a member of Alpha")
Id = sess("ida")
Id.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG}"})
Bo.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
SP = f"org:{ORG}"


def trashed_sheet(s, title):
    sid = s.post(B + "/api/sheets", json={"title": title, "space": SP}).json().get("id")
    check(sid and s.delete(B + f"/api/sheets/{sid}").ok, f"(7) setup: table {title} in the trash")
    return sid


def trashed_page(s, path):
    pid = s.post(B + "/api/wiki/pages", json={"space": SP, "path": path, "body": "text"}).json().get("id")
    check(pid and s.delete(B + f"/api/wiki/pages/{pid}").ok, f"(7) setup: page {path} in the trash")
    return pid


S_BOB, S_IDA = trashed_sheet(Bo, "Bob's table"), trashed_sheet(Id, "Ida's table")
r = Id.post(B + "/api/sheets/purge", json={"space": SP, "ids": [S_BOB]})
check(r.status_code == 403 and dbx("SELECT 1 FROM sheets WHERE id=?", (S_BOB,)), f"(7) ida cannot delete bob's table for good ({r.status_code})")
check(Id.post(B + "/api/sheets/purge", json={"space": SP, "ids": [S_IDA]}).json().get("ids") == [S_IDA], "(7) ida deletes her own one for good")
check(Bo.post(B + "/api/sheets/purge", json={"space": SP, "ids": [S_BOB]}).json().get("ids") == [S_BOB], "(7) bob (admin) deletes it")
P_BOB, P_IDA = trashed_page(Bo, "Bob page 6297"), trashed_page(Id, "Ida page 6297")
r = Id.post(B + "/api/wiki/purge", json={"space": SP, "ids": [P_BOB]})
check(r.status_code == 403 and dbx("SELECT 1 FROM wiki_pages WHERE id=?", (P_BOB,)), f"(7) ida cannot delete bob's page for good ({r.status_code})")
check(Id.post(B + "/api/wiki/purge", json={"space": SP, "ids": [P_IDA]}).json().get("ids") == [P_IDA], "(7) ida deletes her own page for good")
check(Bo.post(B + "/api/wiki/purge", json={"space": SP, "ids": [P_BOB]}).json().get("ids") == [P_BOB], "(7) bob (admin) deletes it")
# 2.1364.0 (#6297 7, Fable review job/5254 F3): put into the trash by ida is not hers -- two steps would cross the admin's limit
T_BOB = Bo.post(B + "/api/sheets", json={"title": "Bob's second table", "space": SP}).json().get("id")
check(T_BOB and Id.delete(B + f"/api/sheets/{T_BOB}").ok, "(7) setup: ida puts bob's table into the trash")
r = Id.post(B + "/api/sheets/purge", json={"space": SP, "ids": [T_BOB]})
check(r.status_code == 403 and dbx("SELECT 1 FROM sheets WHERE id=?", (T_BOB,)), f"(7) ida cannot then delete it for good ({r.status_code})")
check(Bo.post(B + "/api/sheets/purge", json={"space": SP, "ids": [T_BOB]}).json().get("ids") == [T_BOB], "(7) bob (admin) can")
Q_BOB = Bo.post(B + "/api/wiki/pages", json={"space": SP, "path": "Bob page two 6297", "body": "text"}).json().get("id")
check(Q_BOB and Id.delete(B + f"/api/wiki/pages/{Q_BOB}").ok, "(7) setup: ida puts bob's page into the trash")
r = Id.post(B + "/api/wiki/purge", json={"space": SP, "ids": [Q_BOB]})
check(r.status_code == 403 and dbx("SELECT 1 FROM wiki_pages WHERE id=?", (Q_BOB,)), f"(7) ida cannot then delete the page for good ({r.status_code})")
check(Bo.post(B + "/api/wiki/purge", json={"space": SP, "ids": [Q_BOB]}).json().get("ids") == [Q_BOB], "(7) bob (admin) can")

# ==== 6 (Fable review job/5254 F2): the same person by address and by name in the file store's dialog
kt.proved()
SH2 = Bo.post(B + "/api/sheets", json={"title": "Rates 6297", "space": SP}).json().get("id")
r = Bo.post(B + f"/api/sheets/{SH2}/shares", json={"email": "ida@example.com", "role": "read"})
check(SH2 and r.status_code == 201, f"(6) setup: bob shares an organisation table with ida's address {r.text[:120]}")
N2 = dbx("SELECT id FROM fs_nodes WHERE kind='ref' AND ref_kind='sheet' AND ref_id=?", (SH2,))[0][0]


def ida_rows():
    return dbx("SELECT id, role FROM fs_shares WHERE node_id=? AND user_id=?", (N2, IDA))


check(len(ida_rows()) == 1, f"(6) setup: the address is bound to ida's account ({ida_rows()})")
r = Bo.post(B + f"/api/files/nodes/{N2}/shares", json={"user_id": IDA, "role": "edit"})
rows = ida_rows()
check(r.status_code == 201 and len(rows) == 1 and rows[0][1] == "edit", f"(6) by name: one row of ida, its role changed ({r.status_code} {rows})")
check(any(x.get("user_id") == IDA for x in r.json().get("shares", [])), "(6) the file store's dialog lists ida's share by name")
check([tuple(x) for x in dbx("SELECT user_id FROM sheet_shares WHERE sheet_id=? AND email_key<>''", (SH2,))] == [(None,)],
      "(6) the address stays, open again (as in the table's own dialog)")
r = Bo.delete(B + f"/api/files/shares/{rows[0][0] if rows else 0}")
check(r.ok and not ida_rows(), f"(6) and the file store's dialog ends it ({r.status_code})")

sys.exit(kt.done("p21364_c_haertung"))
