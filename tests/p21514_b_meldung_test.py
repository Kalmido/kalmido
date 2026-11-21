#!/usr/bin/env python3
# kalmido-suite: fresh
# freelancer-matrix: report
# tenant-matrix: report
"""(#7531): "Report a problem" through the shared intake (kalmido/integrations/meldung.py), reported by a person
WITHOUT an organisation into the project the server admin chose (as a hosting customer into the operator's project):
 - without a chosen project: 409 {none} (the client keeps its old way)
 - required fields: bug = problem + expected, wish = want + blocker (how optional); unknown keys refused
 - a filled report with a context block full of contents: the task has the fields in its notes, the block is its own attachment
   kalmido-context.json with only page (no query), version, device, cut errors and failed requests (path without query, no
   bodies) - no input texts, no tokens, no mail addresses, nothing of the block in the notes
 - the reporter's state follows the task by the fixed table: open -> working (assignee) -> fixed (done) / wont (won't do)
 - the list of a place: own reports and those of people sharing an organisation; never another organisation's
 - the context left out: no attachment
 - the inbound webhook takes the same block (an attachment, the notes untouched); a block that is no object is a 400
usage: p21514_b_meldung_test.py <datadir>"""
import json
import os
import sys
import time

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from kt import B, check, done, fresh, setup, sess  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

fresh()
A = setup("alice", "Alice")
ME = A.get(B + "/api/state").json()["me"]
ORG = A.post(B + "/api/orgs", json={"name": "Alpha Studio"}).json()["id"]
FID, Fr = freelancer(B, A)
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob", "password": "password123", "email": "bob@example.com", "orgs": [ORG]})
assert r.ok, r.text
Bo = sess("bob")
BUG = {"kind": "bug", "problem": "The save button does nothing\nIt stays grey", "expected": "It saves the invoice"}

r = Fr.post(B + "/api/reports", json=BUG)
check(r.status_code == 409 and r.json().get("none") is True, f"no project chosen: 409 none ({r.status_code} {r.text[:200]})")

P = A.post(B + "/api/lists", json={"name": "Support"}).json()["id"]
check(A.patch(B + f"/api/lists/{P}/error-hook", json={"state": "on"}).ok, "setup: error reports on in the support project")
check(A.patch(B + "/api/admin/settings", json={"client_errors_list": P}).ok, "setup: the admin chooses it for reports")
check(Fr.get(B + "/api/about").json().get("client_errors") is True, "the freelancer's client knows reports are taken")

for bad, why in (({"kind": "bug", "problem": "only"}, "bug without expected"), ({"kind": "wish", "want": "export"}, "wish without blocker"),
                 ({**BUG, "colour": "red"}, "an unknown key"), ({"kind": "other", "problem": "a", "expected": "b"}, "an unknown kind"),
                 ({**BUG, "context": 5}, "a block that is no object"), ({**BUG, "want": "x"}, "a wish field on a bug")):
    r = Fr.post(B + "/api/reports", json=bad)
    check(r.status_code == 400, f"refused: {why} ({r.status_code} {r.text[:160]})")

SECRET, TOK = "Geheimer Kundentext Mueller", "tok_live_abcdef"
CTX = {"route": "#t/123?q=Geheimer", "version": "2.1499.0", "token": TOK, "cookie": "sid=1", "inputs": {"title": SECRET},
       "device": {"platform": "Linux", "browser": "Firefox 140", "touch": False, "width": 1280, "height": 800, "dpr": 1, "serial": SECRET},
       "errors": [{"msg": f"TypeError: '{SECRET}' is not a function for bob@example.com", "place": "https://host.example/static/js/app.js?v=1:10:2", "stack": SECRET}],
       "requests": [{"method": "GET", "path": f"/api/tasks/5?token={TOK}&q=x", "status": 500, "ms": 120, "body": SECRET},
                    {"method": "TRACE", "path": "/api/x", "status": 500, "ms": 1},
                    # reader F8: names in a path (a call sheet's job, a wiki file, a folder watcher) never go along - only the route
                    {"method": "GET", "path": "/api/team/dispo/callsheet/Dreh-Mueller-Werbung", "status": 404, "ms": 3},
                    {"method": "GET", "path": "/api/wiki/files/7/Vertrag-Mueller.pdf", "status": 404, "ms": 4},
                    {"method": "GET", "path": "/api/docs/folder-watcher/Scanner-Mueller", "status": 404, "ms": 5},
                    {"method": "GET", "path": "/api/no-such-thing/Mueller", "status": 404, "ms": 6},
                    # F11: the browser sends the real path (clienterr.js CER_REQ), a nested route keeps its pattern; a path masked
                    # in the browser (cer_reqPath, only for the dialog) would find no route and fall away
                    {"method": "GET", "path": "/api/account/export", "status": 500, "ms": 7},
                    {"method": "GET", "path": "/api/account/_", "status": 500, "ms": 8}]}
r = Fr.post(B + "/api/reports", json={**BUG, "place": "#t/n", "context": CTX})
check(r.status_code == 201 and r.json().get("task_id") is None and r.json().get("context") is True, f"reported: 201, the task stays hidden ({r.status_code} {r.text[:200]})")


def tasks_of(lid):
    return [t for t in A.get(B + "/api/state").json().get("tasks", []) if t.get("list_id") == lid]


ts = [t for t in tasks_of(P) if t["title"].startswith("The save button")]
check(len(ts) == 1, f"one task in the support project ({[t['title'] for t in tasks_of(P)]})")
T = A.get(B + f"/api/tasks/{ts[0]['id']}").json() if ts else {}
note = T.get("content") or ""
check("It stays grey" in note and "It saves the invoice" in note and "Expected" in note, f"the fields in the notes: {note[:300]}")
check(not any(x in note for x in ("Firefox", "#t/123", "TypeError", "/api/tasks/5")), "nothing of the block in the notes")
att = [a for a in T.get("attachments", []) if a.get("name") == "kalmido-context.json"]
check(len(att) == 1, f"the block is its own attachment ({T.get('attachments')})")
raw = A.get(B + f"/api/attachments/{att[0]['id']}").text if att else ""
try:
    blk = json.loads(raw)
except ValueError:
    blk = {}
check(blk.get("route") == "#t/123" and blk.get("version") == "2.1499.0", f"page without its query, the version ({blk})")
check(blk.get("device") == {"platform": "Linux", "browser": "Firefox 140", "touch": False, "width": 1280, "height": 800, "dpr": 1}, f"the device, nothing else ({blk.get('device')})")
check(blk.get("requests") == [{"method": "GET", "path": "/api/tasks/<int:tid>", "status": 500, "ms": 120},
                             {"method": "GET", "path": "/api/team/dispo/callsheet/<job>", "status": 404, "ms": 3},
                             {"method": "GET", "path": "/api/wiki/files/<int:fid>/<path:name>", "status": 404, "ms": 4},
                             {"method": "GET", "path": "/api/docs/folder-watcher/<name>", "status": 404, "ms": 5},
                             {"method": "GET", "path": "/api/account/export", "status": 500, "ms": 7}],
      f"failed requests: the route's pattern only - no query, no body, no names, unknown paths dropped ({blk.get('requests')})")
check("Mueller" not in raw and "/tasks/5" not in raw, f"no name and no id of a request in the block ({raw[:300]})")
e0 = (blk.get("errors") or [{}])[0]
check(e0.get("place") == "/static/js/app.js:10:2" and "TypeError" in e0.get("msg", ""), f"the error with its place ({e0})")
check(not any(x in raw for x in (SECRET, "Geheimer", TOK, "sid=1", "bob@example.com", "inputs", "stack")), f"no contents, tokens or addresses in the block: {raw[:400]}")

TID = ts[0]["id"] if ts else 0
# tenant: POST /api/reports
r = Fr.get(B + f"/api/tasks/{TID}")
check(r.status_code in (403, 404), f"the reporter gets no rights in the chosen project: her report's task stays closed to her ({r.status_code})")


def state():
    j = Fr.get(B + "/api/reports?place=%23t/n").json()
    m = [x for x in j.get("items", []) if x["title"].startswith("The save button")]
    return j, (m[0] if m else {})


j, it = state()
check(j.get("target") is True and it.get("state") == "open" and it.get("mine") and it.get("here") and it.get("kind") == "bug", f"the reporter sees it: open ({j})")
check(set(it) == {"kind", "title", "place", "state", "created_at", "mine", "here"}, f"only the own title and the state, never the task ({it})")
A.patch(B + f"/api/tasks/{TID}", json={"title": "Internal: invoice save broken on staging", "assignee_id": ME["id"]})
j, it = state()
check(it.get("state") == "working" and it.get("title") == "The save button does nothing", f"assigned: working, the reporter's own title stays ({it})")
A.post(B + f"/api/tasks/{TID}/complete", json={"status": 2})
check(state()[1].get("state") == "fixed", f"done: fixed ({state()[1]})")
A.post(B + f"/api/tasks/{TID}/complete", json={"status": -1})
check(state()[1].get("state") == "wont", f"won't do: wont ({state()[1]})")
A.post(B + f"/api/tasks/{TID}/complete", json={"status": 0})
check(state()[1].get("state") == "working", "reopened: working again")

# the list of a place: an organisation member sees the reports of her organisation there, never the freelancer's
r = A.post(B + "/api/reports", json={"kind": "wish", "want": "Export the list", "blocker": "No button", "how": "A CSV", "place": "#t/n", "context": None})
check(r.status_code == 201 and r.json().get("context") is False, f"alice reports a wish without the block ({r.text[:200]})")
wt = [t for t in tasks_of(P) if t["title"] == "Export the list"]
check(wt and not [a for a in A.get(B + f"/api/tasks/{wt[0]['id']}").json().get("attachments", []) if a.get("name") == "kalmido-context.json"], "left out: no attachment")
check("A CSV" in (A.get(B + f"/api/tasks/{wt[0]['id']}").json().get("content") or "") if wt else False, "the optional field in the notes")
bi = Bo.get(B + "/api/reports?place=%23t/n").json().get("items", [])
check(len(bi) == 1 and bi[0]["kind"] == "wish" and not bi[0]["mine"], f"bob (alice's organisation) sees alice's report here, not the freelancer's ({bi})")
# reader F1: the words of a report stay the reporter's - a colleague sees kind, state and time, never the title
check(bi and bi[0]["title"] == "" and bi[0]["state"] == "open", f"bob sees no title of alice's report ({bi})")
ai = A.get(B + "/api/reports?place=%23t/n").json().get("items", [])
check([x["title"] for x in ai if x["mine"]] == ["Export the list"], f"alice sees her own title ({ai})")
# tenant: GET /api/reports
fi = Fr.get(B + "/api/reports?place=%23t/n").json().get("items", [])
check([x["title"] for x in fi] == ["The save button does nothing"], f"the freelancer sees only her own ({fi})")
oth = Fr.get(B + "/api/reports?place=%23today").json().get("items", [])
check(len(oth) == 1 and oth[0]["here"] is False, f"another place: her own report still listed, not as here ({oth})")
# reader F2: a word in the address after the view (a tag, a name) never goes along - only the view and numbers
r = Fr.post(B + "/api/reports", json={**BUG, "place": "#tag/kunde-mueller/7", "context": {"route": "#tag/kunde-mueller/7?q=x"}})
check(r.status_code == 201 and r.json()["report"]["place"] == "#tag/_/7", f"the place without the tag's name ({r.text[:200]})")
tg = [t for t in tasks_of(P) if t["title"].startswith("The save button")]
tga = [a for t in tg for a in A.get(B + f"/api/tasks/{t['id']}").json().get("attachments", []) if a.get("name") == "kalmido-context.json"]
traw = "".join(A.get(B + f"/api/attachments/{a['id']}").text for a in tga)
check("#tag/_/7" in traw and "mueller" not in traw, f"the block's page without the tag's name ({traw[:300]})")

# the inbound webhook takes the same block
h = A.post(B + f"/api/lists/{P}/hooks-in", json={"name": "monitor"}).json()
HH = {"X-Kalmido-Hook-Token": h.get("token", ""), "Content-Type": "application/json"}
r = requests.post(B + "/api/hooks/in", headers=HH, data=json.dumps({"title": "Monitor: checkout down", "notes": "Seen at 03:00", "context": CTX}))
check(r.status_code == 201, f"webhook with a block: 201 ({r.status_code} {r.text[:200]})")
W = A.get(B + f"/api/tasks/{r.json().get('id')}").json() if r.ok else {}
wa = [a for a in W.get("attachments", []) if a.get("name") == "kalmido-context.json"]
wraw = A.get(B + f"/api/attachments/{wa[0]['id']}").text if wa else ""
check(W.get("content") == "Seen at 03:00" and wa and '"route": "#t/123"' in wraw and SECRET not in wraw and TOK not in wraw, f"webhook: notes untouched, the clean block attached ({W.get('content')!r} {wraw[:200]})")
n0 = len(tasks_of(P))
r = requests.post(B + "/api/hooks/in", headers=HH, data=json.dumps({"title": "Bad block", "context": [1, 2]}))
check(r.status_code == 400 and len(tasks_of(P)) == n0, f"webhook: a block that is no object -> 400, no task ({r.status_code})")

# reader F7: a long word (60 KB, no space) is cut before the patterns - over the webhook's context and over /api/reports
LONG = "x" * 61440
t0 = time.monotonic()
r = requests.post(B + "/api/hooks/in", headers=HH, data=json.dumps({"title": "Long error", "context": {"errors": [{"msg": LONG}]}}))  # one 60 KB text: the hook takes 64 KB
dt = time.monotonic() - t0
check(r.status_code == 201 and dt < 5, f"webhook: a 60 KB error text in the block is quick ({r.status_code}, {dt:.1f} s)")
t0 = time.monotonic()
r = Fr.post(B + "/api/reports", json={**BUG, "context": {"errors": [{"msg": LONG}] * 5}})
dt = time.monotonic() - t0
check(r.status_code == 201 and dt < 5, f"/api/reports: a 60 KB error text in the block is quick ({r.status_code} {r.text[:120]}, {dt:.1f} s)")
r = Fr.post(B + "/api/client-errors", json={"msg": LONG, "src": "/static/js/app.js", "line": 1})
check(r.status_code < 500, f"/api/client-errors with a 60 KB text: no hang, no error ({r.status_code})")
sys.exit(done("p21514_b_meldung"))
