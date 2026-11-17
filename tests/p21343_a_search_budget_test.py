#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1343.0 (#6406, audit #4765): the general search on a time budget, the caps of the expensive searches. Own container
(KALMIDO_SEARCH_BUDGET_MS=0: one area per request, so the chain of follow-up requests is walked; KALMIDO_SEARCH_OPEN_MAX=2:
at most two sealed texts opened per search). Invented names only.
 - GET /api/search (the palette's first request): the tasks and at most one group, the areas not reached in pending
 - GET /api/search?kind=groups&groups=<kinds>: each answer at least one more area, the rest pending again; walked to the end,
   the groups hold what the palette shows (contact, event, note, knowledge page of a word only in their content)
 - kind=groups refuses an unknown area or tasks (400); ?groups= (empty) gives the tasks alone (no groups, no pending)
 - sealed texts: a 5-letter word found by its 4-letter prefix opens at most KALMIDO_SEARCH_OPEN_MAX texts (the newest);
   the whole 8-letter word (its own stored prefix, no opening) still finds every page
freelancer-matrix: search (a person without an organisation walks the same chain and finds her own contact)
usage: p21343_a_search_budget_test.py <datadir>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kt  # noqa: E402
from kt import B, check, until  # noqa: E402
from freelancer_fixture import FEATURES, freelancer  # noqa: E402

D = "2026-12-03"


def made(r, what):
    check(r.status_code in (200, 201), f"setup: {what} {r.status_code} {r.text[:160]}")
    return r.json() if r.ok else {}


def first(s, q, **kw):
    r = s.get(B + "/api/search", params={"q": q, "limit": 8, "glimit": 6, **kw})
    check(r.status_code == 200, f"GET /api/search {q}: {r.status_code} {r.text[:160]}")
    return r.json() if r.ok else {}


def chain(s, q):
    """The palette's way: the first request, then kind=groups for what is pending, until nothing is -> (groups, requests)."""
    j = first(s, q)
    groups, n = dict(j.get("groups") or {}), 1
    pend = j.get("pending") or []
    while pend and n < 20:
        r = s.get(B + "/api/search", params={"q": q, "kind": "groups", "groups": ",".join(pend), "glimit": 6})
        check(r.status_code == 200, f"kind=groups {pend}: {r.status_code} {r.text[:160]}")
        k = r.json() if r.ok else {}
        got = set(k.get("groups") or {}) | set(k.get("pending") or [])
        check(got <= set(pend), f"a follow-up answers only the kinds asked for {got} vs {pend}")
        check(len(k.get("pending") or []) < len(pend), f"each follow-up gets further {pend} -> {k.get('pending')}")
        groups.update(k.get("groups") or {})
        pend, n = k.get("pending") or [], n + 1
    return groups, n


def ids(hits):
    return {h.get("id") for h in hits or []}


kt.fresh(env={"KALMIDO_SEARCH_BUDGET_MS": "0", "KALMIDO_SEARCH_OPEN_MAX": "2"}, prefix="P21343A")
r = kt.sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"})
assert r.ok, r.text
A = kt.sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "collab_all": True, "modules": ["comments"]})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
FID, Fr = freelancer(B, A)
Fr.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
LP = made(A.post(B + "/api/lists", json={"name": "Garten"}), "a project")["id"]
SP = f"org:{ORG}"

# one word in the content of four areas (contact, event, note, knowledge page) and a task
W = "Holunderstrauch"
T1 = made(A.post(B + "/api/tasks", json={"title": "Wochenplan", "list_id": LP, "content": f"{W} schneiden"}), "a task")["id"]
CT = made(A.post(B + "/api/contacts", json={"fn": "Erika Beispiel", "note": f"kennt den {W}"}), "a contact")
CT = (CT.get("contact") or CT)["id"]
EV = made(A.post(B + "/api/events", json={"title": "Treffen", "start": f"{D}T10:00", "end": f"{D}T11:00", "tz": "Europe/Berlin",
                                            "description": f"{W} pflanzen"}), "an event")
EV = (EV.get("event") or EV)["id"]
NT = made(A.post(B + f"/api/lists/{LP}/notes", json={"title": "Protokoll", "body": f"{W} gekauft"}), "a note")
NT = (NT.get("note") or NT)["id"]
WP = made(A.post(B + "/api/wiki/pages", json={"space": SP, "path": "Garten/Hecke", "body": f"Der {W} blüht"}), "a page")["id"]

# ================================================================== the budget: one area per request, the rest pending
j = first(A, "holunderstrauch")
check(T1 in {h["task"]["id"] for h in j.get("hits", [])}, "the first request still has the tasks")
check(len(j.get("groups") or {}) <= 1, f"budget 0: at most one area searched in the first request {list(j.get('groups') or {})}")
check(len(j.get("pending") or []) >= 3, f"... the areas not reached are named in pending {j.get('pending')}")
check("tasks" not in (j.get("pending") or []), "tasks are never pending (they are the answer itself)")
g, n = chain(A, "holunderstrauch")
check(n >= 4, f"the chain took several requests ({n})")
check(CT in ids(g.get("contacts")), f"the chain finds the contact {list(g)}")
check(EV in ids(g.get("events")), "... the event")
check(NT in ids(g.get("notes")), "... the note")
check(WP in ids(g.get("wiki")), "... the knowledge page")

# ================================================================== the forms of the route
r = A.get(B + "/api/search", params={"q": "holunderstrauch", "kind": "groups", "groups": "nosuch"})
check(r.status_code == 400, f"kind=groups with an unknown area: 400 ({r.status_code})")
r = A.get(B + "/api/search", params={"q": "holunderstrauch", "kind": "groups", "groups": "tasks"})
check(r.status_code == 400, f"kind=groups with tasks: 400 ({r.status_code})")
r = A.get(B + "/api/search", params={"q": "holunderstrauch", "kind": "groups"})
check(r.status_code == 400, f"kind=groups without groups: 400 ({r.status_code})")
j = first(A, "holunderstrauch", groups="")
check(T1 in {h["task"]["id"] for h in j.get("hits", [])} and not j.get("groups") and not j.get("pending"),
      f"groups= (empty): the tasks alone, no groups, nothing pending {sorted(j)}")
r = A.get(B + "/api/search", params={"q": "holunderstrauch", "kind": "groups", "groups": "contacts"})
check(r.ok and CT in ids((r.json().get("groups") or {}).get("contacts")) and not r.json().get("pending"),
      f"kind=groups&groups=contacts: just that area {r.text[:160]}")

# ================================================================== the freelancer: the same chain
FC = made(Fr.post(B + "/api/contacts", json={"fn": "Freia Muster", "note": f"liefert {W}"}), "a contact of the freelancer")
FC = (FC.get("contact") or FC)["id"]
g, _ = chain(Fr, "holunderstrauch")
check(FC in ids(g.get("contacts")) and CT not in ids(g.get("contacts")), f"freelancer: her own contact, not alice's {g.get('contacts')}")

# ================================================================== the cap of opened sealed texts
P = [made(A.post(B + "/api/wiki/pages", json={"space": SP, "path": f"Obst/Seite{i}", "body": f"Brombeermarmelade Nummer {i}"}),
          f"page {i}")["id"] for i in range(3)]


def wiki(q):
    r = A.get(B + "/api/search", params={"kind": "wiki", "q": q})
    return {p["id"] for p in r.json().get("pages", [])} if r.ok else {("error", r.status_code)}


check(until(lambda: wiki("brombeer") == set(P), 60), f"the whole 8-letter word finds every page {wiki('brombeer')}")
got = until(lambda: wiki("bromb") if len(wiki("bromb")) == 2 else None, 60)
check(got == set(P[1:]), f"bromb (found by its prefix, each page opened to check): only the 2 newest opened {wiki('bromb')}")
sys.exit(kt.done("p21343_a_search_budget"))
