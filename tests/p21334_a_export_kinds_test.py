#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1334.0 (#6585, audit #4808 T13; with #6359): what the export guard per kind found missing goes into the exports now, and the
change history follows the objects an archive carries. Invented names only (example.com).
 - the organisation export: the free links (links.json), the history of the objects it carries (history/changes.json) and never
   the history of an object it does not carry (another organisation's task, a row that is gone), the file copies of the
   templates (lists/template_files.json; a copy gone from the disk is named in missing), all named in not_imported
 - freelancer-matrix: a person without an organisation: the account export carries the details of the private documents
   (private-documents/documents/meta.json + notes.json, nothing of the trash), the private links (a contact's task, a free
   link), the project's bell, the remembered shopping items, the sign-in addresses, the own account row, the history of the
   own changes; a template's file gone from the disk is named in missing (was left out silently); the import's preview names
   the documents as staying behind
 - a member: the account export carries the own note on an organisation's document and the memberships (Art. 15)
Starts its OWN container (workspaces mode, no server key: the archives are plain ZIPs). usage: p21334_a_export_kinds_test.py <datadir>"""
# freelancer-matrix: tasks
import io
import json
import sys
import zipfile

import kt
from freelancer_fixture import FEATURES, freelancer
from kt import B, check, dbx, su_get

kt.fresh(prefix="P21334A", env={"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_API_RATE": "100000"})
kt.docker_logs_on_first_fail()
TS = "2026-11-10T10:00:00+00:00"


def ok(r, what):
    check(r.status_code in (200, 201, 202, 204), f"{what} {r.status_code} {r.text[:200]}")
    try:
        return r.json()
    except ValueError:
        return {}


def one(rows):
    return rows[0][0] if rows else None


def unzip(raw):
    try:
        return zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return None


def rows_of(z, name):
    if z is None or name not in z.namelist():
        return []
    t = z.read(name).decode()
    try:
        v = json.loads(t)
    except ValueError:
        v = [json.loads(x) for x in t.splitlines() if x.strip()]
    return v if isinstance(v, list) else []


# ================================================================== the organisation export
A = kt.setup()
ALICE = A.get(B + "/api/state").json()["me"]["id"]
kt.proved()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ORGS = {}
for name in ("Alpha Quelle", "Beta Fremd"):
    r = A.post(B + "/api/admin/orgs", json={"name": name, "admin_id": ALICE})
    check(r.status_code == 201, f"setup: organisation {name} {r.text[:120]}")
    ORGS[name] = r.json().get("id")
ORG, ORGB = ORGS["Alpha Quelle"], ORGS["Beta Fremd"]
T = {}
for org, tag in ((ORG, "alpha"), (ORGB, "beta")):
    A.patch(B + "/api/settings", json={"workspace": f"org:{org}"})
    lid = ok(A.post(B + "/api/lists", json={"name": f"Projekt {tag}", "org_id": org}), f"setup: list of {tag}").get("id")
    T[tag] = [ok(A.post(B + "/api/tasks", json={"title": f"Aufgabe {tag} {i}", "list_id": lid}), f"setup: task {i} of {tag}").get("id")
              for i in (1, 2)]
ta, tb = T.get("alpha") or [0, 0], T.get("beta") or [0, 0]
# the core's rows directly (this suite checks the exports, not the areas' routes): a free link between alpha's tasks, the history
# of alpha's task, a history row of alpha that names beta's task, one that names a message that is gone
dbx("INSERT INTO obj_links(org_id, src_kind, src_id, dst_kind, dst_id, rel, note, created_by, created_at) "
    "VALUES(?, 'task', ?, 'task', ?, 'related', 'frei verknuepft', ?, ?)", (ORG, ta[0], ta[1], ALICE, TS))
HIST = "INSERT INTO obj_history(kind, ref_id, org_id, user_id, action, vals_before, vals_after, created_at, updated_at) " \
       "VALUES(?, ?, ?, ?, 'update', CAST(? AS JSONB), CAST(? AS JSONB), ?, ?)"
dbx(HIST, ("task", ta[0], ORG, ALICE, '{"title": "Alpha alt"}', '{"title": "Alpha neu"}', TS, TS))
dbx(HIST, ("task", tb[0], ORG, ALICE, '{"title": "Fremd alt"}', '{"title": "Fremd neu"}', TS, TS))
dbx(HIST, ("tchat_msg", 987654321, ORG, ALICE, '{"body": "Gruppe alt"}', '{"body": "Gruppe neu"}', TS, TS))
TPL = one(dbx("INSERT INTO templates(owner_id, org_id, kind, name, created_at, updated_at) VALUES(?, ?, 'task', 'Vorlage Alpha', ?, ?) RETURNING id",
              (ALICE, ORG, TS, TS)))
TF = one(dbx("INSERT INTO template_files(template_id, user_id, node_key, name, path, created_at) VALUES(?, ?, 'n1', 'weg.txt', 'tpl/gone/weg.txt', ?) "
             "RETURNING id", (TPL, ALICE, TS)))
check(TPL and TF, f"setup: a template of alpha with a file copy that is gone from the disk {TPL} {TF}")

A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
ok(A.post(B + f"/api/orgs/{ORG}/export"), "the export of alpha starts")
kt.until(lambda: A.get(B + f"/api/orgs/{ORG}/export").json().get("state") in ("done", "failed"), timeout=240)
check(A.get(B + f"/api/orgs/{ORG}/export").json().get("state") == "done", "the export of alpha is done")
z = unzip(su_get(A, B + f"/api/orgs/{ORG}/export/file").content)
check(z is not None, "the organisation export is a plain ZIP")
names = set(z.namelist()) if z else set()
lk = rows_of(z, "links.json")
check([(r.get("src_id"), r.get("dst_id"), r.get("rel"), r.get("note")) for r in lk] == [(ta[0], ta[1], "related", "frei verknuepft")],
      f"links.json: the free link of alpha in the core's columns {lk}")
hs = rows_of(z, "history/changes.json")
hb = json.dumps(hs)
check("Alpha neu" in hb, f"history/changes.json: the history of alpha's task {hb[:300]}")
check("Fremd neu" not in hb and "Gruppe neu" not in hb,
      f"history/changes.json: never the history of an object the archive does not carry (beta's task, a message that is gone) {hb[:300]}")
tfs = rows_of(z, "lists/template_files.json")
check([r.get("id") for r in tfs] == [TF], f"lists/template_files.json: the template's file copy {tfs}")
man = json.loads(z.read("manifest.json")) if z and "manifest.json" in names else {}
check(any(m.get("file", "").startswith(f"files/templates/{TF}-") for m in man.get("missing") or []),
      f"the manifest names the template's file copy that is gone (missing) {man.get('missing')}")
ni = " | ".join(man.get("not_imported") or [])
check(all(f in ni for f in ("history/changes.json", "links.json", "lists/template_files.json", "agents/rules.json")),
      f"not_imported names the files no import takes over {ni}")
check(z is not None and "agents/rules.json" in names and "hub/mailbox_rules.json" in names,
      f"the organisation's agent rules and mailbox rules are files of the archive {sorted(n for n in names if n.startswith(('agents/', 'hub/')))}")

# ================================================================== freelancer-matrix: the account export of a person without organisation
FID, Fr = freelancer(B, A)
FL = ok(Fr.post(B + "/api/lists", json={"name": "Frei Projekt"}), "freelancer: own list").get("id")
FT = [ok(Fr.post(B + "/api/tasks", json={"title": f"Frei Aufgabe {i}", "list_id": FL}), f"freelancer: own task {i}").get("id") for i in (1, 2)]
bk = ok(Fr.post(B + "/api/books", json={"name": "Frei Kontakte"}), "freelancer: own address book").get("id")
co = ok(Fr.post(B + "/api/contacts", json={"book_id": bk, "fn": "Kim Frei"}), "freelancer: own contact").get("id")
dbx("INSERT INTO obj_links(src_kind, src_id, dst_kind, dst_id, rel, extra, created_by, created_at) VALUES('contact', ?, 'task', ?, 'contact', "
    "CAST(? AS JSONB), ?, ?)", (co, FT[0], '{"kind": "waiting"}', FID, TS))
dbx("INSERT INTO obj_links(src_kind, src_id, dst_kind, dst_id, rel, created_by, created_at) VALUES('task', ?, 'task', ?, 'related', ?, ?)",
    (FT[0], FT[1], FID, TS))
# the private document store: a document with its details and a note; one in the trash
WS = f"u{FID}"
DOC = one(dbx("INSERT INTO fs_nodes(owner_id, kind, name, created_at, updated_at) VALUES(?, 'file', 'rechnung.pdf', ?, ?) RETURNING id", (FID, TS, TS)))
GONE = one(dbx("INSERT INTO fs_nodes(owner_id, kind, name, created_at, updated_at, deleted_at) VALUES(?, 'file', 'weg.pdf', ?, ?, ?) RETURNING id",
               (FID, TS, TS, TS)))
for nid, title in ((DOC, "Frei Rechnung"), (GONE, "Weg Rechnung")):
    dbx("INSERT INTO doc_meta(node_id, ws, title, created_at, updated_at) VALUES(?, ?, ?, ?, ?)", (nid, WS, title, TS, TS))
dbx("INSERT INTO obj_comments(kind, ref_id, user_id, body, created_at) VALUES('doc_note', ?, ?, 'Frei Notiz', ?)", (DOC, FID, TS))
# a project's bell, a remembered shopping item, a sign-in address, a change of my own, a template whose file copy is gone
dbx("INSERT INTO obj_follow(kind, ref_id, user_id, mode, created_at) VALUES('list', ?, ?, 'mute', ?)", (FL, FID, TS))
SEC = one(dbx("SELECT id FROM sections WHERE list_id=? ORDER BY id LIMIT 1", (FL,)))
if SEC:
    dbx("INSERT INTO shop_memory(list_id, item, section_id, at) VALUES(?, 'Frei Milch', ?, ?)", (FL, SEC, TS))
dbx("INSERT INTO login_ips(ip, user_id, at) VALUES('192.0.2.7', ?, ?)", (FID, TS))
dbx(HIST, ("task", FT[0], None, FID, '{"title": "Frei alt"}', '{"title": "Frei Aufgabe 1"}', TS, TS))
FTPL = one(dbx("INSERT INTO templates(owner_id, kind, name, created_at, updated_at) VALUES(?, 'task', 'Frei Vorlage', ?, ?) RETURNING id", (FID, TS, TS)))
FTF = one(dbx("INSERT INTO template_files(template_id, user_id, node_key, name, path, created_at) VALUES(?, ?, 'n1', 'frei.txt', 'tpl/gone/frei.txt', ?) "
              "RETURNING id", (FTPL, FID, TS)))
check(DOC and GONE and FTPL and FTF, f"setup: the freelancer's documents and template {DOC} {GONE} {FTPL} {FTF}")


ok(Fr.post(B + "/api/account/export", json={}), "freelancer: account export starts")
kt.until(lambda: Fr.get(B + "/api/account/export").json().get("state") != "running", timeout=240)
check(Fr.get(B + "/api/account/export").json().get("state") == "done", "freelancer: account export done")
fz = unzip(su_get(Fr, B + "/api/account/export/file").content)
check(fz is not None, "freelancer: the account export is a ZIP")
fn = set(fz.namelist()) if fz else set()
meta = rows_of(fz, "private-documents/documents/meta.json")
check([(m.get("node_id"), m.get("title")) for m in meta] == [(DOC, "Frei Rechnung")],
      f"freelancer: the details of the private document, nothing of the trash {meta}")
notes = rows_of(fz, "private-documents/documents/notes.json")
check([(n.get("node_id"), n.get("text")) for n in notes] == [(DOC, "Frei Notiz")], f"freelancer: the note on the private document {notes}")
pl = rows_of(fz, "data/private_links.json")
check({(x.get("src_kind"), x.get("rel")) for x in pl} == {("contact", "contact"), ("task", "related")},
      f"freelancer: the private links (a contact's task, a free link) {pl}")
lb = rows_of(fz, "data/list_bell.json")
check([(x.get("list_id"), x.get("level")) for x in lb] == [(FL, "mute")], f"freelancer: the project's bell {lb}")
sm = rows_of(fz, "data/shop_memory.json")
check(not SEC or [x.get("item") for x in sm] == ["Frei Milch"], f"freelancer: the remembered shopping item (#6359) {sm}")
ips = rows_of(fz, "data/login_ips.json")
check("192.0.2.7" in [x.get("ip") for x in ips], f"freelancer: the sign-in addresses (+ the test's own sign-in) {ips}")
acc = rows_of(fz, "data/account.json")
check(len(acc) == 1 and acc[0].get("id") == FID and "password_hash" not in acc[0] and "totp_secret" not in acc[0],
      f"freelancer: the own account row, never a secret {acc}")
mh = json.dumps(rows_of(fz, "data/my_history.json"))
check("Frei alt" in mh, f"freelancer: the history of my own change {mh[:200]}")
fman = json.loads(fz.read("manifest.json")) if fz and "manifest.json" in fn else {}
check(any(m.get("file", "").startswith(f"files/template_files/{FTF}-") for m in fman.get("missing") or []),
      f"freelancer: a template's file copy gone from the disk is named in missing {fman.get('missing')}")
fni = " | ".join(fman.get("not_imported") or [])
check("private-documents/" in fni and "private_links" in fni and "my_history" in fni,
      f"freelancer: not_imported names the documents, the links and the history {fni}")
check((fman.get("private_documents") or {}).get("documents") == 1, f"freelancer: the manifest counts the private documents {fman.get('private_documents')}")

# ================================================================== a member: what I wrote in an organisation, my memberships (Art. 15)
ODOC = one(dbx("INSERT INTO fs_nodes(owner_id, org_id, kind, name, created_at, updated_at) VALUES(?, ?, 'file', 'org.pdf', ?, ?) RETURNING id",
               (ALICE, ORG, TS, TS)))
dbx("INSERT INTO obj_comments(kind, ref_id, org_id, user_id, body, created_at) VALUES('doc_note', ?, ?, ?, 'Alice in Alpha', ?)", (ODOC, ORG, ALICE, TS))
ok(A.post(B + "/api/account/export", json={}), "alice: account export starts")
kt.until(lambda: A.get(B + "/api/account/export").json().get("state") != "running", timeout=240)
check(A.get(B + "/api/account/export").json().get("state") == "done", "alice: account export done")
az = unzip(su_get(A, B + "/api/account/export/file").content)
on = rows_of(az, "data/org_doc_notes.json")
check([(n.get("node_id"), n.get("text")) for n in on] == [(ODOC, "Alice in Alpha")], f"alice: my note on an organisation's document {on}")
ms = rows_of(az, "data/memberships.json")
check({m.get("org_name") for m in ms} >= {"Alpha Quelle", "Beta Fremd"}, f"alice: the organisations I am a member of {ms}")

sys.exit(kt.done("p21334_a_export_kinds"))
