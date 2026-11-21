#!/usr/bin/env python3
# kalmido-suite:
"""2.1507.0 part A (#6297, audit #4741): the security hardening round, points 2-7 (point 1 in part B, point 6 in #7646), one
section each, each red without its fix. One container (start.sh, mode workspaces, a server key); invented names only
(example.com).
freelancer-matrix: office
 2 a text that only starts like a sealed value ("kenc1:...") is sealed like any other (the ledger entry of a person without
   an organisation reads, changes and deletes again); a real sealed value is kept, one of another place sealed anew
 3 restoring a deleted task comment / team chat message: the author does not undo a project admin's delete; not in a frozen
   DM; not as a read-only person of the organisation (each was 200 before)
 4 a mail reply through the own address token of a read-only member with a colleague's forged From: no comment, a note
 5 another person's own ticket types: only the ones their private project I see offers, without note template, switched off
   ones or id (was: every own type of that person)
 7 the organisation's table / knowledge trash: a writing member deletes for good only what she made, one at a time (was:
   any one, one at a time; put into the trash by her is not enough); its admin any
usage: p21507_a_haertung_test.py <datadir>"""
import base64
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
import testclock  # noqa: E402
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import B, CT, check, dbx, sess  # noqa: E402

kt.fresh(env={"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ORGCRYPT_DELAY": "0",
              "KALMIDO_SECRET_KEY": base64.b64encode(os.urandom(32)).decode()}, prefix="P21507A")
A = kt.setup()
ids = {}
for u in ("bob", "carl", "hanna", "ida"):
    r = A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": kt.PASSWORD, "email": f"{u}@example.com"})
    assert r.ok, r.text
    ids[u] = r.json()["id"]
BOB, CARL, HANNA, IDA = (ids[u] for u in ("bob", "carl", "hanna", "ida"))
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": BOB})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
dbx("DELETE FROM org_members WHERE org_id=? AND user_id<>?", (ORG, BOB))
check(A.patch(B + f"/api/admin/orgs/{ORG}", json={"members_add": [CARL, HANNA, IDA]}).ok, "setup: carl, hanna and ida are members of Alpha")
kt.proved()  # the accounts proved their addresses (a mail reply finds a person only by a proved address, section 4)


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
check(r.ok and mine and mine[0].get("text", "").lstrip("​") == FAKE, f"(2) the year reads (was 500) and shows the text {r.status_code}")
r = Fr.put(B + f"/api/office/books/ledger/entries/{E.get('id')}", json={"text": FAKE + "B", "expect_updated_at": E.get("updated_at")})
check(r.ok, f"(2) the entry can be changed {r.status_code}")
check(Fr.delete(B + f"/api/office/books/ledger/entries/{E.get('id')}").ok, "(2) and deleted")
out = py_in_app(f"from kalmido.core import orgcrypt as oc\nv = oc.oc_enc(c, {ORG}, 't.c', 'geheim')\n"
                f"print('KEEP', oc.oc_enc(c, {ORG}, 't.c', v) == v, oc.oc_dec(c, {ORG}, 't.c', oc.oc_enc(c, {ORG}, 't.c', '{FAKE}')).lstrip(chr(8203)) == '{FAKE}',"
                f" oc.oc_enc(c, {ORG}, 't.d', v) != v)")
check("KEEP True True True" in out, f"(2) a real sealed value is kept, a fake one sealed, one of another place sealed anew: {out[-300:]}")

# ==== 4: a mail reply of a read-only member with a forged From
Bo, Ca, Ha = sess("bob"), sess("carl"), sess("hanna")
for s_ in (Bo, Ca, Ha):
    s_.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG}"})
L = Bo.post(B + "/api/lists", json={"name": "Hardening", "org_id": ORG}).json().get("id")
check(L and Bo.put(B + f"/api/lists/{L}/members", json={"user_id": CARL, "role": "edit"}).ok
      and Bo.put(B + f"/api/lists/{L}/members", json={"user_id": HANNA, "role": "edit"}).ok, "(4) setup: bob's project, carl and hanna edit")
T = Bo.post(B + "/api/tasks", json={"list_id": L, "title": "Check"}).json().get("id")
check(T and Bo.put(B + f"/api/orgs/{ORG}/members", json={"user_id": HANNA, "role": "readonly"}).ok, "(4) setup: a task, hanna read-only in Alpha")
dbx("INSERT INTO task_mail(task_id,msg_id,sender,kind,created_at) VALUES(?,?,'',?,now())", (T, "<t6297@example.com>", "out"))
n0 = dbx("SELECT COUNT(*) FROM obj_comments WHERE kind='task' AND ref_id=?", (T,))[0][0]
MAIL = "From: Bob <bob@example.com>\nTo: hanna+tok@example.com\nSubject: Re: Check\nIn-Reply-To: <t6297@example.com>\nMessage-ID: <f6297@example.com>\n\nForged"
out = py_in_app("import email\nfrom kalmido.integrations.taskmail import tmr_take\n"
                f"print('TAKE', tmr_take(c, email.message_from_string({MAIL!r}), None, {HANNA}, 'token')[0])")
take = [x for x in out.splitlines() if x.startswith(("TAKE", "Traceback", "  File"))] or [out[-300:]]
check("TAKE note" in out, f"(4) hanna's token with bob's address as From: a note, no comment ({take})")
check(dbx("SELECT COUNT(*) FROM obj_comments WHERE kind='task' AND ref_id=?", (T,))[0][0] == n0, "(4) no comment on the task")
out = py_in_app("import email\nfrom kalmido.integrations.taskmail import tmr_take\n"
                f"print('TAKE', tmr_take(c, email.message_from_string({MAIL!r}), None, {BOB}, 'token')[0])")
take = [x for x in out.splitlines() if x.startswith(("TAKE", "Traceback", "  File"))] or [out[-300:]]
check("TAKE comment" in out, f"(4) bob's own token: still a comment ({take})")

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

# ==== 3: restoring a comment / a team chat message (bob's project L, carl edits, hanna read-only in Alpha since section 4)
Bo.get(B + "/api/team")
ROOM = next((x["id"] for x in Ca.get(B + "/api/team").json().get("rooms", []) if x.get("list_id") == L), None)
check(ROOM, f"(3) setup: the project's channel {ROOM}")


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

# ==== 7: the trash of an organisation's tables and knowledge pages (ida a writing member of Alpha, bob its admin)
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
# put into the trash by ida is not hers -- two steps would cross the admin's limit
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

sys.exit(kt.done("p21507_a_haertung"))
