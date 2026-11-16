#!/usr/bin/env python3
"""2.192.0 C (#2514): fills an OLDER release's empty test server with typical invented data and dumps its database -- the
fixture tests/fixtures/upgrade/<version>.sql.gz (+ <version>.json: what that release showed through its API) that
p2192_c_upgrade_test.py starts the current server on. Written against the API of 2.101.0 (the release of the first dump);
it runs inside the old release's tests/ folder (tools/make_upgrade_dump.sh copies it there), so it needs nothing but
requests and docker (no kt.py: that came later).

    python3 upgrade_seed.py <datadir>     (the old server runs: start.sh; KALMIDO_TEST_PORT as in start.sh)
    # shots: 'P2192C_DUMP_SHOTS'          the folder the dump + JSON are written to (default: tests/fixtures/upgrade)
    # 2.589.0 (#4359): UPG_SETUP_CODE = the one-time setup code of a server that asks for one (an installation by install.sh;
    # the test container runs without), UPG_VERSION = the old server's version when the script does not run inside its tree
    # (tools/install_upgrade_check.py runs the candidate's copy against the release before it)

Data (invented, addresses @example.com): instance admin alice with the organisation "Nordwind Studio", member bob, frida
without an organisation (her own private workspace and personal office); an org project and a private list with tasks (due
date + time, repeat rule, subtasks, a done task), comments of two people, an attachment, an org office (client, quotation
with items, invoice from it, finalized), frida's personal office (client + quotation), time entries, a personal agent.
2.1265.0 (#6287): one real object of each kind the shared core took over (KERN): a project tag and an organisation label on a
task, a reaction, a review comment, a document note, a knowledge page with two versions, a playbook with two versions, a
template and a section template. The script also runs in an older release's tree (the upgrade probe copies it into the live
tag): a step whose route that release lacks (404 / 405) is skipped and named in <version>.json "kern_skipped" -- the suite
then compares exactly what was seeded and says what it leaves out."""
import gzip
import json
import os
import subprocess
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("KALMIDO_TEST_DATA") or os.path.join(HERE, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
PW = "password123"
FEATURES = ("cal,timeline,matrix,habits,pomo,kanban,collab,stats,time,progress,deps,fields,comments,events,contacts,files,docs,"
            "clients,office,workload,forms,wiki")
OUT = os.environ.get("P2192C_DUMP_SHOTS") or os.path.join(HERE, "fixtures", "upgrade")


def ok(r, what):
    assert r.status_code < 300, f"{what}: {r.status_code} {r.text[:300]}"
    return r.json() if r.content else {}


def login(user):
    s = requests.Session()
    s.headers.update(H)
    ok(s.post(B + "/api/auth/login", json={"username": user, "password": PW}), "login " + user)
    return s


s0 = requests.Session()
s0.headers.update(H)
SETUP = {"username": "alice", "display_name": "Alice Admin", "password": PW}
if os.environ.get("UPG_SETUP_CODE"):  # 2.589.0 (#4359)
    SETUP["setup_code"] = os.environ["UPG_SETUP_CODE"]
ok(s0.post(B + "/api/auth/setup", json=SETUP), "setup")
A = login("alice")
ok(A.post(B + "/api/admin/setup", json={"org_name": "Nordwind Studio", "lang": "en", "collab_all": True, "time_all": True,
                                       "modules": ["cal", "habits", "pomo", "stats", "deps", "fields"]}),
   "admin setup")
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
ok(A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG}"}), "alice settings")
BOB = ok(A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob Beispiel", "password": PW,
                                        "email": "bob@example.com", "orgs": [ORG]}), "bob")["id"]
FRIDA = ok(A.post(B + "/api/users", json={"username": "frida", "display_name": "Frida Frei", "password": PW,
                                          "email": "frida@example.com", "orgs": []}), "frida")["id"]
Bo, Fr = login("bob"), login("frida")
ok(Bo.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"}), "bob settings")
ok(Fr.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"}), "frida settings")

# lists + tasks
TEAM = ok(A.post(B + "/api/lists", json={"name": "Nordwind Projekte", "org_id": ORG, "kind": "project", "time_tracking": True}), "team")["id"]
ok(A.put(B + f"/api/lists/{TEAM}/members", json={"user_id": BOB, "role": "edit"}), "bob in team")
PRIV = ok(A.post(B + "/api/lists", json={"name": "Alice privat", "org_id": None}), "alice private")["id"]
T1 = ok(A.post(B + "/api/tasks", json={"list_id": TEAM, "title": "Imagefilm schneiden", "due": "2026-03-04", "due_time": "18:30"}), "t1")["id"]
ok(A.patch(B + f"/api/tasks/{T1}", json={"repeat": "FREQ=WEEKLY;BYDAY=MO"}), "t1 repeat")
for t in ("Rohschnitt", "Farbkorrektur"):
    ok(A.post(B + "/api/tasks", json={"list_id": TEAM, "title": t, "parent_id": T1}), "subtask")
T2 = ok(A.post(B + "/api/tasks", json={"list_id": TEAM, "title": "Musik lizenzieren", "due": "2026-04-01"}), "t2")["id"]
T3 = ok(A.post(B + "/api/tasks", json={"list_id": TEAM, "title": "Angebot schicken"}), "t3")["id"]
ok(A.post(B + f"/api/tasks/{T3}/complete", json={}), "t3 done")
for t in ("Steuerunterlagen sortieren", "Zahnarzt anrufen"):
    ok(A.post(B + "/api/tasks", json={"list_id": PRIV, "title": t, "repeat": "FREQ=MONTHLY" if t[0] == "S" else ""}), "private task")
C1 = ok(A.post(B + f"/api/tasks/{T1}/comments", json={"body": "Erste Fassung bis Freitag"}), "comment alice").get("id")  # #6287
ok(Bo.post(B + f"/api/tasks/{T1}/comments", json={"body": "Ton kommt am Donnerstag"}), "comment bob")
ok(A.post(B + f"/api/tasks/{T1}/attachments", files={"file": ("briefing.txt", b"Briefing Imagefilm\n" * 10, "text/plain")}), "attachment")
FL = ok(Fr.post(B + "/api/lists", json={"name": "Frida Kunden", "kind": "project", "time_tracking": True}), "frida list")["id"]
FT = ok(Fr.post(B + "/api/tasks", json={"list_id": FL, "title": "Website-Texte", "due": "2026-05-15"}), "frida task")["id"]
ok(Fr.post(B + f"/api/tasks/{FT}/comments", json={"body": "Entwurf liegt bei"}), "frida comment")

# office: the org's (alice = org admin) and frida's personal one
ok(A.put(B + "/api/office/settings", json={"company_fields": {"name": "Nordwind Studio GmbH", "street": "Hafenweg 1", "zip": "20457",
                                                             "city": "Hamburg", "country": "DE", "tax_number": "12/345/67890",
                                                             "iban": "DE02120300000000202051", "bic": "BYLADEM1001"}}), "org office settings")
CL = ok(A.post(B + "/api/clients", json={"name": "Beispielkunde AG", "street": "Marktstraße 5", "zip": "50667", "city": "Köln",
                                         "country": "DE", "org_id": ORG}), "org client")["id"]
Q = ok(A.post(B + "/api/office/docs", json={"kind": "offer", "project_title": "Imagefilm", "client_id": CL,
                                            "service_from": "2026-02-01", "service_to": "2026-02-28"}), "offer")["id"]
ok(A.put(B + f"/api/office/docs/{Q}/items", json={"items": [{"title": "Drehtag", "qty": 2, "rate": 900},
                                                            {"title": "Schnitt", "qty": 3, "rate": 650}]}), "offer items")
INV = ok(A.post(B + f"/api/office/docs/{Q}/invoice"), "invoice")["id"]
ok(A.post(B + f"/api/office/docs/{INV}/finalize"), "finalize")
FCL = ok(Fr.post(B + "/api/clients", json={"name": "Kleinkunde GbR", "city": "Berlin", "country": "DE"}), "frida client")["id"]
FQ = ok(Fr.post(B + "/api/office/docs", json={"kind": "offer", "project_title": "Texte", "client_id": FCL}), "frida offer")["id"]
ok(Fr.put(B + f"/api/office/docs/{FQ}/items", json={"items": [{"title": "Text", "qty": 4, "rate": 120}]}), "frida items")

# time entries + agent
ok(A.post(B + "/api/time/entries", json={"task_id": T1, "start": "2026-02-10T09:00", "minutes": 90, "note": "Sichtung"}), "time alice")
ok(Bo.post(B + "/api/time/entries", json={"task_id": T1, "start": "2026-02-11T10:00", "minutes": 45}), "time bob")
ok(Fr.post(B + "/api/time/entries", json={"list_id": FL, "start": "2026-02-12T08:00", "minutes": 30}), "time frida")
ok(A.put(B + "/api/admin/agent-policy", json={"user_agents": True}), "agent policy")
AG = ok(A.post(B + "/api/my/agents", json={"username": "nordbot", "display_name": "Nordwind Bot", "scopes": ["read", "tasks:write"]}), "agent")["id"]
ok(A.put(B + f"/api/lists/{TEAM}/members", json={"user_id": AG, "role": "edit"}), "agent in team")


# 2.1265.0 (#6287): the kinds of the shared core (KERN_ITEMS, the same names in tests/upgrade_views.py)
KERN_ITEMS = ("project_tag", "label", "reaction", "review_comment", "doc_note", "wiki", "playbook", "template", "section_template")
KERN_IDS, KERN_SKIP = {}, {}


class Missing(Exception):
    """The release has no such route: the step is skipped, not failed."""


def kok(r, what):
    if r.status_code in (404, 405):
        raise Missing(f"{what}: {r.status_code} {r.text[:120]}")
    return ok(r, what)


def kern(name, fn):
    try:
        KERN_IDS[name] = fn()
    except Missing as e:
        KERN_SKIP[name] = str(e)
        print(f"upgrade_seed: {name} skipped, this release lacks the route ({e})")


def wait_doc(nid):
    """The document's processing has finished (its state, not a fixed time)."""
    end = time.time() + 120
    while time.time() < end:
        r = A.get(B + f"/api/docs/{nid}")
        if r.ok and r.json().get("state") in ("done", "failed"):
            return
        time.sleep(0.5)
    raise AssertionError(f"document {nid} not processed within 120 s")


def seed_project_tag():
    kok(A.post(B + f"/api/lists/{TEAM}/tags", json={"name": "Schnitt", "color": "#3b82f6"}), "project tag")
    ok(A.patch(B + f"/api/tasks/{T2}", json={"ltags": ["Schnitt"]}), "project tag on a task")
    return {"list": TEAM, "task": T2}


def seed_label():
    kok(A.post(B + "/api/org-labels", json={"org_id": ORG, "name": "Dringend", "color": "#f87171"}), "label")
    ok(A.patch(B + f"/api/tasks/{T2}", json={"ltags": (["Schnitt"] if "project_tag" in KERN_IDS else []) + ["Dringend"]}), "label on a task")
    return {"org": ORG, "task": T2}


def seed_reaction():
    kok(Bo.post(B + f"/api/comments/{C1}/reactions", json={"emoji": "heart", "on": True}), "reaction")
    return {"task": T1, "comment": C1}


def seed_review_comment():
    ok(A.patch(B + "/api/settings", json={"features": FEATURES + ",videos"}), "alice: reviews on")
    vid = kok(A.post(B + "/api/videos", json={"title": "Imagefilm Rohschnitt", "url": "https://vimeo.com/123456789", "list_id": TEAM}),
              "review")["id"]
    kok(A.post(B + f"/api/videos/{vid}/comments", json={"body": "Bei Sekunde zwölf heller", "at_sec": 12}), "review comment")
    return {"video": vid}


def seed_doc_note():
    r = kok(A.post(B + "/api/docs", data={"ws": "private"}, files=[("files", ("lieferschein.txt", b"Lieferschein Nordwind\n" * 5, "text/plain"))]),
            "document")
    nid = r["ids"][0]
    wait_doc(nid)
    kok(A.post(B + f"/api/docs/{nid}/notes", json={"text": "Geprüft, liegt im Ordner Belege"}), "document note")
    return {"doc": nid}


def seed_wiki():
    pid = kok(A.post(B + "/api/wiki/pages", json={"space": f"org:{ORG}", "path": "Handbuch/Abläufe", "body": "Schnitt vor Ton."}),
              "knowledge page")["id"]
    ok(A.patch(B + f"/api/wiki/pages/{pid}", json={"body": "Schnitt vor Ton. Farbe zuletzt."}), "page, version 1")
    ok(Bo.patch(B + f"/api/wiki/pages/{pid}", json={"body": "Schnitt vor Ton. Farbe zuletzt. Abnahme mit dem Kunden."}), "page, version 2 (bob)")
    vs = kok(A.get(B + f"/api/wiki/pages/{pid}/versions"), "page versions").get("versions") or []
    assert len(vs) >= 2, f"knowledge page: two versions expected, {vs}"
    return {"page": pid}


def seed_playbook():
    kok(A.put(B + f"/api/lists/{TEAM}/playbook", json={"text": "Kunden binnen eines Tages antworten."}), "playbook")
    ok(A.put(B + f"/api/lists/{TEAM}/playbook", json={"text": "Kunden binnen eines Tages antworten. Freitags kein Versand."}), "playbook, version 2")
    return {"list": TEAM}


def seed_template():
    return {"template": kok(A.post(B + "/api/templates", json={"list_id": PRIV, "name": "Privat-Vorlage"}), "template")["id"]}


def seed_section_template():
    return {"template": kok(A.post(B + "/api/section-templates", json={"name": "Schnittphasen", "sections": ["Rohschnitt", "Feinschnitt"]}),
                            "section template")["id"]}


for _name in KERN_ITEMS:
    kern(_name, globals()["seed_" + _name])


def kern_view(name, ids):
    """What the release shows of a KERN item -- the same as tests/upgrade_views.py kern_view (keep both alike)."""
    if name in ("project_tag", "label"):
        st = A.get(B + "/api/state").json()
        task = next((t for t in st["tasks"] if t["id"] == ids["task"]), {})
        if name == "project_tag":
            lst = next((x for x in st["lists"] if x["id"] == ids["list"]), {})
            return {"list": sorted(t["name"] for t in lst.get("tags") or [] if t["name"] == "Schnitt"), "task": sorted(task.get("ltags") or [])}
        labels = kok(A.get(B + "/api/org-labels", params={"org_id": ids["org"]}), "labels")["labels"]
        return {"labels": sorted(x["name"] for x in labels), "task": sorted(task.get("ltags") or [])}
    if name == "reaction":
        cs = kok(A.get(B + f"/api/tasks/{ids['task']}/timeline"), "timeline")["comments"]
        c = next((x for x in cs if x["id"] == ids["comment"]), {})
        return sorted([x["emoji"], x["count"], sorted(u["name"] for u in x["users"])] for x in c.get("reactions") or [])
    if name == "review_comment":
        v = kok(A.get(B + f"/api/videos/{ids['video']}"), "review")
        return {"title": v["title"], "comments": sorted([c["body"], c.get("at_sec"), c.get("author_id")] for c in v["comments"])}
    if name == "doc_note":
        return [n["text"] for n in kok(A.get(B + f"/api/docs/{ids['doc']}/notes"), "notes")["notes"]]
    if name == "wiki":
        base = B + f"/api/wiki/pages/{ids['page']}"
        vs = sorted(kok(A.get(base + "/versions"), "versions")["versions"], key=lambda v: v["no"])
        return {"body": kok(A.get(base), "page")["body"], "versions": [kok(A.get(base + f"/versions/{v['id']}"), "version")["body"] for v in vs]}
    if name == "playbook":
        base = B + f"/api/lists/{ids['list']}/playbook"
        vs = sorted(v["version"] for v in kok(A.get(base + "/versions"), "playbook versions")["versions"])
        return {"text": kok(A.get(base), "playbook")["text"], "versions": [kok(A.get(base + f"/versions/{v}"), "version")["text"] for v in vs]}
    if name == "template":
        ts = kok(A.get(B + "/api/templates"), "templates")["templates"]
        return sorted([t["kind"], t["name"], t.get("count")] for t in ts if t["id"] == ids["template"])
    if name == "section_template":
        ts = kok(A.get(B + "/api/section-templates"), "section templates")["templates"]
        return sorted([t["name"], t["sections"]] for t in ts if t["id"] == ids["template"])
    raise AssertionError(name)


KERN = {}
for _name, _ids in KERN_IDS.items():
    try:
        KERN[_name] = kern_view(_name, _ids)
    except Missing as e:
        KERN_SKIP[_name] = f"read back: {e}"
print(f"upgrade_seed: core kinds seeded {sorted(KERN)}, skipped {sorted(KERN_SKIP)}")


# what this release shows: the suite compares the upgraded server's answers with it
def view(s):
    st = s.get(B + "/api/state").json()
    lists = {x["id"]: x["name"] for x in st["lists"]}
    tasks = sorted((lists.get(t["list_id"], "?"), t["title"], t.get("due") or "", t.get("due_time") or "", t.get("repeat") or "",
                    bool(t.get("parent_id")), t.get("status") or 0,
                    sorted(a["name"] for a in t.get("attachments") or [])) for t in st["tasks"])
    return {"lists": sorted(lists.values()), "tasks": tasks}


def comments(s, tid):
    return sorted(c["body"] for c in s.get(B + f"/api/tasks/{tid}/timeline").json()["comments"])


def docs(s):
    out = []
    for kind in ("offer", "invoice"):
        for d in s.get(B + "/api/office/docs", params={"kind": kind}).json()["docs"]:
            full = s.get(B + f"/api/office/docs/{d['id']}").json()
            out.append({"id": d["id"], "kind": kind, "number": full.get("number") or "", "net": full["totals"]["net"],
                        "gross": full["totals"]["gross"]})
    return sorted(out, key=lambda d: d["id"])


def minutes(s):
    es = s.get(B + "/api/time/entries", params={"scope": "all", "from": "2026-01-01"}).json()["entries"]
    return sorted(round((e.get("seconds") or e.get("minutes", 0) * 60) / 60) for e in es)


EXP = {
    "version": os.environ.get("UPG_VERSION") or open(os.path.join(HERE, "..", "VERSION")).read().strip(),  # 2.589.0 (#4359)
    "password": PW, "org": ORG, "ids": {"team": TEAM, "private": PRIV, "t1": T1, "t2": T2, "frida_list": FL, "frida_task": FT,
                                        "offer": Q, "invoice": INV, "frida_offer": FQ, "agent": AG, "bob": BOB, "frida": FRIDA},
    "users": {u: view(s) for u, s in (("alice", A), ("bob", Bo), ("frida", Fr))},
    "comments": {"t1": comments(A, T1), "frida_task": comments(Fr, FT)},
    "docs": {"alice": docs(A), "frida": docs(Fr)},
    "clients": {"alice": sorted(c["name"] for c in A.get(B + "/api/clients").json()["clients"]),
                "frida": sorted(c["name"] for c in Fr.get(B + "/api/clients").json()["clients"])},
    "minutes": {"alice": minutes(A), "frida": minutes(Fr)},
    "agents": sorted(a["username"] for a in A.get(B + "/api/my/agents").json()["agents"]),
    "kern": KERN, "kern_ids": KERN_IDS, "kern_skipped": KERN_SKIP,  # 2.1265.0 (#6287)
}
assert EXP["docs"]["alice"] and EXP["docs"]["frida"] and EXP["minutes"]["alice"], EXP

with open(os.path.join(DATA, ".kalmido-db"), encoding="utf-8") as f:
    DBC, DBN = f.read().split()
r = subprocess.run(["docker", "exec", DBC, "pg_dump", "-U", "kalmido", "-d", DBN, "--no-owner", "--no-privileges"],
                   capture_output=True, check=True)
os.makedirs(OUT, exist_ok=True)
v = EXP["version"]
with gzip.GzipFile(os.path.join(OUT, v + ".sql.gz"), "wb", 9, mtime=0) as f:
    f.write(r.stdout)
with open(os.path.join(OUT, v + ".json"), "w", encoding="utf-8") as f:
    json.dump(EXP, f, ensure_ascii=False, indent=1, sort_keys=True)
    f.write("\n")
print(json.dumps({k: EXP[k] for k in ("version", "ids", "agents")}))
print(f"upgrade_seed: dump {len(r.stdout)} bytes -> {OUT}/{v}.sql.gz")
print("upgrade_seed: 1 ok, 0 failed")
