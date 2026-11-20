#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#6356, audit #4773 F8): an account's and an organisation's delete for good take their leftovers along - with the retention
switch OFF (the test container's default), so no orphan sweep helps.
 - a person (frida, WITHOUT an organisation) goes: the stored pictures of her bookmarks (attachments/bookmarks/), the files of
   her agent chats on both sides (attachments/chat/<agent>-<person>/, a message of hers with a file, and a folder of an agent
   of hers), her account import upload (exports/account-import/<id>) are gone from the disk; another person's agent rule
   that quoted her keeps the rule, without the quote and her id
 - an organisation goes: the pictures of its bookmarks are gone; another person's private bookmark picture stays
freelancer-matrix: own
alice (instance admin), frida (a person without an organisation), bob (agent rule, private bookmark). Invented values only.
Red without the fix: every file listed stays after the delete, the quote stays in agent_rules.
usage: p6356_purge_rest_test.py <datadir>   (P6356_NOSTART=1: the container runs already)"""
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check, dbx, done  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from obj_probe import in_app  # noqa: E402

kt.fresh(env={"KALMIDO_INSTANCE_MODE": "workspaces"}, prefix="P6356")
A = kt.setup()
FID, F = freelancer(B, A)
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob", "password": "password123", "email": "bob@example.com"})
assert r.ok, r.text
BOB = r.json()["id"]
Bo = kt.sess("bob")
Bo.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})  # personal agents on (the server's switch)


def files(*rels):
    """Writes the files (paths relative to the data folder in the container) as the server's user."""
    code = "import os\n" + "".join(f"p = os.path.join('/data', {x!r})\nos.makedirs(os.path.dirname(p), exist_ok=True)\nopen(p, 'w').write('x')\n" for x in rels)
    out = in_app(code)
    assert "Traceback" not in out, out


def there(rel):
    """Does the file / folder exist in the container's data folder (relative path)?"""
    out = in_app(f"import os\nprint('THERE', os.path.exists(os.path.join('/data', {rel!r})))")
    assert "THERE" in out, out
    return "THERE True" in out


def bookmark(uid, org=None, img=""):
    return dbx("INSERT INTO bookmarks(user_id, org_id, url, url_key, title, image, image_mime, preview, created_at, updated_at) "
               "VALUES(?, ?, 'https://example.com/a', 'example.com/a', 'Example', ?, 'image/png', 'done', now(), now()) RETURNING id",
               (uid, org, img))[0][0]


# ---------------------------------------------------------------- setup: frida's leftovers
BMF = bookmark(FID)
dbx("UPDATE bookmarks SET image=? WHERE id=?", (f"bookmarks/{BMF}-aaaa.png", BMF))
files(f"attachments/bookmarks/{BMF}-aaaa.png")
r = F.post(B + "/api/my/agents", json={"username": "frida-bot", "display_name": "Frida Bot"})
check(r.status_code == 201, f"setup: frida's agent {r.text[:160]}")
FAG = r.json()["id"]
r = F.post(B + f"/api/agents/{FAG}/chat", data={"body": "With a file"}, files={"file": ("note.txt", b"note\n", "text/plain")})
check(r.ok, f"setup: frida sends her agent a file {r.text[:160]}")
CHATP = dbx("SELECT f.path FROM chat_files f JOIN agent_chat m ON m.id=f.message_id WHERE m.user_id=?", (FID,))
check(len(CHATP) == 1 and there("attachments/" + CHATP[0][0]), f"setup: the chat file is on the disk {CHATP}")
files(f"attachments/chat/{FAG}-{FID}/old-without-row.txt", f"attachments/chat/{FAG}-{BOB}/bobs.txt",
      f"exports/account-import/{FID}/upload.part")
r = Bo.post(B + "/api/my/agents", json={"username": "bob-bot", "display_name": "Bob Bot"})
check(r.status_code == 201, f"setup: bob's agent {r.text[:160]}")
BAG = r.json()["id"]
files(f"attachments/chat/{BAG}-{BOB}/keep.txt")
RULE = dbx("INSERT INTO agent_rules(agent_id, body, source_kind, source_user_id, source_excerpt, created_by, created_at, updated_at) "
           "VALUES(?, 'Always answer in English', 'chat', ?, 'frida wrote: please always in English', ?, now(), now()) RETURNING id",
           (BAG, FID, BOB))[0][0]

# ---------------------------------------------------------------- frida goes
r = A.delete(B + f"/api/users/{FID}")
check(r.ok, f"frida's account is deleted {r.status_code} {r.text[:200]}")
check(not there(f"attachments/bookmarks/{BMF}-aaaa.png"), "#6356: her bookmark's picture is gone")
check(not there("attachments/" + CHATP[0][0]) and not there(f"attachments/chat/{FAG}-{FID}"), "#6356: her agent chat folder is gone (files with and without a row)")
check(not there(f"attachments/chat/{FAG}-{BOB}"), "#6356: the folder of her agent with someone else goes too (the agent went with her)")
check(not there(f"exports/account-import/{FID}"), "#6356: her account import upload is gone")
check(there(f"attachments/chat/{BAG}-{BOB}/keep.txt"), "bob's own agent chat stays")
row = dbx("SELECT body, source_excerpt, source_user_id FROM agent_rules WHERE id=?", (RULE,))
check(row and row[0][0] == "Always answer in English" and row[0][1] == "" and row[0][2] is None,
      f"#6356: bob's agent keeps the rule, without frida's words and id {row}")

# ---------------------------------------------------------------- an organisation goes
ORG = A.post(B + "/api/admin/orgs", json={"name": "Example Studio", "admin_id": BOB}).json()["id"]
BMO = bookmark(BOB, ORG)
dbx("UPDATE bookmarks SET image=? WHERE id=?", (f"bookmarks/{BMO}-bbbb.png", BMO))
BMB = bookmark(BOB)
dbx("UPDATE bookmarks SET image=? WHERE id=?", (f"bookmarks/{BMB}-cccc.png", BMB))
files(f"attachments/bookmarks/{BMO}-bbbb.png", f"attachments/bookmarks/{BMB}-cccc.png")
r = A.delete(B + f"/api/admin/orgs/{ORG}?confirm=1")
check(r.ok and not dbx("SELECT 1 FROM orgs WHERE id=?", (ORG,)), f"the organisation is deleted {r.status_code} {r.text[:200]}")
check(not there(f"attachments/bookmarks/{BMO}-bbbb.png"), "#6356: the organisation's bookmark picture is gone")
check(there(f"attachments/bookmarks/{BMB}-cccc.png"), "bob's private bookmark picture stays")

sys.exit(done("p6356_purge_rest"))
