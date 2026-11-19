#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1432 (#6399): a write outside the task lists wakes only the people who can see it, not every open tab of the instance.
Invented people and texts only.
 - GET /api/version vs (#2507) after a write in office (a client), files (a folder), contacts (an address book + a contact)
   and an agent's status: the members of the writer's organisation see it (vs = the new version), a member of another
   organisation and a person without one skip it (vs unchanged below v)
 - the person without an organisation: her own writes wake only her own devices; once she is in a list with a member of
   another organisation, writes of either wake the other too (the lists they share), nobody else
 - an agent's status reaches the people of the lists it is in (and their organisation), not the rest
 - instance-wide paths (admin) still wake everyone
usage: p6399_wake_scope_test.py <datadir>"""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kt  # noqa: E402
from kt import B, check, sess  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

FEATURES = "cal,collab,comments,events,fields,progress,office,clients,contacts"

A = kt.setup()
ORG = {}
for name in ("Alpha", "Beta"):
    r = A.post(B + "/api/admin/orgs", json={"name": name})
    assert r.status_code in (200, 201), r.text
    ORG[name] = r.json()["id"]
uid = {}
for u, o in (("bob", "Alpha"), ("dave", "Alpha"), ("carl", "Beta")):
    r = A.post(B + "/api/users", json={"orgs": [ORG[o]], "username": u, "display_name": u.title(), "password": "password123",
                                       "email": f"{u}@example.com"})
    assert r.ok, r.text
    uid[u] = r.json()["id"]
Bo, Da, Ca = sess("bob"), sess("dave"), sess("carl")
for s in (A, Bo, Da, Ca):
    assert s.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEATURES}).ok
FID, Fr = freelancer(B, A, features=FEATURES)  # the own key of a person without an organisation
uid["frida"] = FID
P = {"bob": Bo, "dave": Da, "carl": Ca, "frida": Fr}  # alice (the instance admin) is left out: her memberships are the setup's


def ver(s):
    j = s.get(B + "/api/version").json()
    return j["v"], j.get("vs")


def made(r, what):
    check(r.status_code in (200, 201), f"setup: {what} ({r.status_code} {r.text[:200]})")
    return r.json() if r.content else {}


def moved(what, fn, see, skip, writer=None):
    """Run the write fn; every person in see gets vs == the change's version, every one in skip keeps vs (below the new v).
    The writer (default: the first word of what) may see a newer own version (#5405: the own step list bumps after it)."""
    before = {k: ver(P[k]) for k in P}
    assert fn() is not False
    after = {k: ver(P[k]) for k in P}
    v = max(x[0] for x in after.values())
    v0 = max(x[0] for x in before.values())
    check(v > v0, f"#6399 {what}: v moved")
    who = writer or what.split()[0].split("'")[0]
    readers = [k for k in see if k != who]
    vc = max((after[k][1] or 0) for k in readers) if readers else v
    for k in see:
        check((after[k][1] or 0) >= vc if k == who else after[k][1] == vc,
              f"#6399 {what}: {k} sees it (vs {before[k][1]} -> {after[k][1]}, change {vc}, v {v})")
    check(vc > v0, f"#6399 {what}: the change's version is newer than every one before ({vc} > {v0})")
    for k in skip:
        check(after[k][1] == before[k][1] and after[k][1] < v,
              f"#6399 {what}: {k} skips it (vs {before[k][1]} -> {after[k][1]}, v {v})")


def ok(r):
    assert r.status_code in (200, 201, 204), r.text
    return True


# ---------------------------------------------------------------- office (a client)
moved("bob adds a client of his organisation", lambda: ok(Bo.post(B + "/api/clients", json={"name": "Alpha Kunde GmbH", "org_id": ORG["Alpha"]})),
      ["bob", "dave"], ["carl", "frida"])
moved("carl adds a client of his organisation", lambda: ok(Ca.post(B + "/api/clients", json={"name": "Beta Kunde GmbH", "org_id": ORG["Beta"]})),
      ["carl"], ["bob", "dave", "frida"])
moved("frida adds her own client", lambda: ok(Fr.post(B + "/api/clients", json={"name": "Privatkunde Eins"})),
      ["frida"], ["bob", "dave", "carl"])

# ---------------------------------------------------------------- files (a folder)
moved("dave makes a folder of his organisation", lambda: ok(Da.post(B + "/api/files/folders", json={"name": "Alpha Ablage", "space": f"org:{ORG['Alpha']}"})),
      ["bob", "dave"], ["carl", "frida"])
FF = made(Fr.post(B + "/api/files/folders", json={"name": "Frida teilt", "space": "private"}), "frida's folder")["id"]
moved("frida makes a folder in her own space", lambda: ok(Fr.post(B + "/api/files/folders", json={"name": "Entwurf", "parent_id": FF})),
      ["frida"], ["bob", "dave", "carl"])
# a membership is an instance-wide path (the person who loses one is in no circle any more): everyone. A file share stays
# inside its workspace; across organisations people meet in a list (carl's private project with frida)
CL = made(Ca.post(B + "/api/lists", json={"name": "Carl und Frida"}), "carl's private list")["id"]
kt.dbx("UPDATE users SET email_proved=lower(COALESCE(email, '')) WHERE email_proved=''")  # (#5669) a share by address needs a proved one
moved("carl adds frida to his private list", lambda: ok(Ca.put(B + f"/api/lists/{CL}/members", json={"email": "frida@example.com", "role": "edit"})),
      list(P), [])
moved("frida makes a folder in her own space", lambda: ok(Fr.post(B + "/api/files/folders", json={"name": "Für Carl", "parent_id": FF})),
      ["frida", "carl"], ["bob", "dave"])
moved("carl makes a folder of his organisation", lambda: ok(Ca.post(B + "/api/files/folders", json={"name": "Beta Ablage", "space": f"org:{ORG['Beta']}"})),
      ["carl", "frida"], ["bob", "dave"])

# ---------------------------------------------------------------- contacts (an address book + a contact)
BK = {}


def book():
    BK["c"] = made(Ca.post(B + "/api/books", json={"name": "Beta Adressen", "org_id": ORG["Beta"]}), "carl's org book")["id"]
    return True


moved("carl makes an address book of his organisation", book, ["carl"], ["bob", "dave", "frida"])
moved("carl adds a contact", lambda: ok(Ca.post(B + "/api/contacts", json={"book_id": BK["c"], "fn": "Erika Beispiel"})),
      ["carl"], ["bob", "dave", "frida"])
BB = made(Bo.post(B + "/api/books", json={"name": "Alpha Adressen", "org_id": ORG["Alpha"]}), "bob's org book")["id"]
moved("bob adds a contact", lambda: ok(Bo.post(B + "/api/contacts", json={"book_id": BB, "fn": "Max Muster"})),
      ["bob", "dave"], ["carl", "frida"])

# ---------------------------------------------------------------- agents (a status change)
ag = made(A.post(B + "/api/admin/agents", json={"scopes": ["write"], "username": "helper", "display_name": "Helper"}), "an agent")
AH = {"Authorization": f"Bearer {ag['token']}"}
AL = made(Bo.post(B + "/api/lists", json={"name": "Alpha board", "org_id": ORG["Alpha"]}), "bob's Alpha board")["id"]
check(ok(Bo.put(B + f"/api/lists/{AL}/members", json={"user_id": ag["id"], "role": "edit"})), "setup: the agent in the Alpha board")
for i, st in enumerate(("working", "idle", "working")):
    moved(f"agent status {st} ({i})", lambda st=st: ok(requests.put(B + "/api/v1/agent/status", headers=AH, json={"status": st, "text": "Läuft" if st == "working" else ""})),
          ["bob", "dave"], ["carl", "frida"], writer="agent")

# ---------------------------------------------------------------- instance-wide stays for everyone
moved("alice creates an organisation (admin)", lambda: ok(A.post(B + "/api/admin/orgs", json={"name": "Gamma"})), list(P), [], writer="alice")

sys.exit(kt.done("p6399_wake_scope"))
