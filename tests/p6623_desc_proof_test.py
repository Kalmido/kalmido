#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1386.0 (#6623): a Yes on an approval card with a bound step is taken only with the proof of the server's description
(GET /api/approvals/diff and GET /api/v1/approvals/diff -> proof, sent as desc_proof); No never needs it. Invented names only.
 - the app's routes (chat card, comment card) and the REST API (a person's own token): Yes without proof -> 409
   desc_proof_needed (+ describe, the address of the description), the card stays open; with the proof -> ok
 - the proof is bound to the card (another card's proof: 409), to the person (another person's proof: 409) and to the words of
   the description (the target renamed since: the old proof 409, a new fetch works)
 - No without proof: ok; a card without a step: Yes without proof ok, no proof in the answer; a decided card: no proof
 - an agent's token never gets the description over the REST API (403)
 - freelancer-matrix: agents (Frida has no organisation)
usage: p6623_desc_proof_test.py <datadir>"""
import sys

import requests

from freelancer_fixture import freelancer
from kt import B, check, done, fresh, setup

V = B + "/api/v1"
D = B + "/api/approvals/diff"

fresh(prefix="P6623")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})
FID, F = freelancer(B, A)
OID, OTTO = freelancer(B, A, "otto")
SCOPES = ["read", "tasks:write", "comments"]


def err(r):
    try:
        e = r.json()["error"]
        return e if isinstance(e, dict) else {"message": e}
    except (ValueError, KeyError, TypeError):
        return {}


r = F.post(B + "/api/my/agents", json={"username": "fridabot", "display_name": "Fridabot", "scopes": SCOPES})
check(r.status_code in (200, 201), f"setup: personal agent {r.status_code} {r.text[:150]}")
FA, FH = r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}
FL = F.post(B + "/api/lists", json={"name": "Frida work"}).json()["id"]
check(F.put(B + f"/api/lists/{FL}/members", json={"user_id": FA, "role": "edit"}).ok, "setup: the project is shared with the agent")
T = F.post(B + "/api/tasks", json={"title": "Plan the shoot", "list_id": FL}).json()["id"]
tk = F.post(B + "/api/me/tokens", json={"name": "script", "scopes": ["read", "comments"]}).json().get("token")
check(bool(tk), "setup: Frida's own access token")
FT = {"Authorization": "Bearer " + (tk or "x")}
STEP = {"method": "PATCH", "path": f"/api/v1/tasks/{T}", "body": {"priority": "high"}}


def card(step=STEP):
    r = requests.post(V + f"/agent/chats/{FID}", headers=FH, json={"approval": {"title": "May I?", **({"step": step} if step else {})}})
    check(r.status_code == 201, f"approval card -> {r.status_code} {r.text[:200]}")
    return r.json().get("id") if r.ok else 0


def proof(s, url=D, **q):
    r = s.get(url, params=q)
    return r.json().get("proof") if r.ok else None


def yes(mid, p=None, s=None):
    b = {"choice_ids": ["yes"], **({"desc_proof": p} if p is not None else {})}
    return (s or F).post(B + f"/api/agents/{FA}/chat/{mid}/choice", json=b)


def answered(mid):
    m = [x for x in F.get(B + f"/api/agents/{FA}/chat").json().get("messages", []) if x.get("id") == mid]
    return bool(m and m[0].get("choice"))


# ================================================================== the app: a chat card
M1, M2 = card(), card()
r = yes(M1)
e = r.json() if r.status_code == 409 else {}
check(r.status_code == 409 and e.get("code") == "desc_proof_needed" and e.get("describe") == f"/api/approvals/diff?chat={M1}",
      f"Yes without proof: 409 desc_proof_needed + describe {r.status_code} {r.text[:200]}")
check(not answered(M1), "the card stays open after the refused Yes")
check(yes(M1, "0" * 40).status_code == 409, "a made-up proof: 409")
P1, P2 = proof(F, chat=M1), proof(F, chat=M2)
check(bool(P1) and bool(P2) and P1 != P2, f"the description answers a proof per card {P1} {P2}")
check(yes(M1, P2).status_code == 409, "the proof of another card: 409")
# the words of the description change (the task's name, its priority now "old -> new"): the old proof no longer counts
r = F.patch(B + f"/api/tasks/{T}", json={"title": "Plan the big shoot", "priority": 1})
check(r.ok, f"setup: the task is renamed, its priority changes {r.status_code} {r.text[:200]}")
P1b = proof(F, chat=M1)
check(bool(P1b) and P1b != P1, "a changed description gives a new proof")
check(yes(M1, P1).status_code == 409, "the old proof of a changed description: 409")
r = yes(M1, P1b)
check(r.ok and answered(M1), f"Yes with the proof of the description now: ok {r.status_code} {r.text[:200]}")
check(proof(F, chat=M1) is None, "a decided card gets no proof")
r = F.post(B + f"/api/agents/{FA}/chat/{M2}/choice", json={"choice_ids": ["no"]})
check(r.ok and answered(M2), f"No without proof: ok {r.status_code} {r.text[:200]}")
M3 = card(step=None)
check(proof(F, chat=M3) is None, "a card without a step: no proof")
check(yes(M3).ok, "a card without a step: Yes without proof")

# ================================================================== the REST API: a person's own token
M4 = card()
r = requests.post(V + f"/agents/{FA}/chat/{M4}/choice", headers=FT, json={"choice_ids": ["yes"]})
check(r.status_code == 409 and err(r).get("code") == "desc_proof_needed" and err(r).get("describe") == f"/api/approvals/diff?chat={M4}",
      f"v1: Yes without proof 409 desc_proof_needed {r.status_code} {r.text[:200]}")
r = requests.get(V + "/approvals/diff", headers=FT, params={"chat": M4})
check(r.ok and r.json().get("proof") and isinstance(r.json().get("desc"), dict), f"v1: GET /approvals/diff with the person's token {r.status_code} {r.text[:200]}")
P4 = r.json().get("proof") if r.ok else None
check(P4 == proof(F, chat=M4), "v1 and the app give the same proof")
check(requests.get(V + "/approvals/diff", headers=FH, params={"chat": M4}).status_code == 403, "v1: an agent's token gets no description (403)")
check(requests.get(V + "/approvals/diff", headers=FT, params={"chat": M4, "x": 1}).status_code == 400, "v1: an unknown parameter 400")
r = requests.post(V + f"/agents/{FA}/chat/{M4}/choice", headers=FT, json={"choice_ids": ["yes"], "desc_proof": P4})
check(r.ok, f"v1: Yes with the proof ok {r.status_code} {r.text[:200]}")

# ================================================================== a comment card (app + REST API), the person binding
check(F.patch(B + f"/api/agents/{FA}/control", json={"level": "routine"}).ok, "setup: routine steps free (a comment)")


def ccard():
    r = requests.post(V + f"/tasks/{T}/comments", headers=FH, json={"body": "May I?", "approval": {"title": "May I?", "step": STEP}})
    check(r.status_code == 201, f"comment card {r.status_code} {r.text[:200]}")
    return r.json().get("id") if r.ok else 0


C1, C2 = ccard(), ccard()
r = F.post(B + f"/api/comments/{C1}/choice", json={"choice_ids": ["yes"]})
check(r.status_code == 409 and r.json().get("code") == "desc_proof_needed", f"comment: Yes without proof 409 {r.status_code} {r.text[:200]}")
# another person who sees the task fetches the description: their proof is not Frida's
check(F.put(B + f"/api/lists/{FL}/members", json={"user_id": OID, "role": "view"}).ok, "setup: Otto sees the project")
PO = proof(OTTO, comment=C1)
check(bool(PO), "the other person gets their own proof")
check(F.post(B + f"/api/comments/{C1}/choice", json={"choice_ids": ["yes"], "desc_proof": PO}).status_code == 409,
      "the proof of another person: 409")
r = F.post(B + f"/api/comments/{C1}/choice", json={"choice_ids": ["yes"], "desc_proof": proof(F, comment=C1)})
check(r.ok, f"comment: Yes with the proof ok {r.status_code} {r.text[:200]}")
r = requests.post(V + f"/comments/{C2}/choice", headers=FT, json={"choice_ids": ["yes"]})
check(r.status_code == 409 and err(r).get("code") == "desc_proof_needed" and err(r).get("describe") == f"/api/approvals/diff?comment={C2}",
      f"v1 comment: Yes without proof 409 {r.status_code} {r.text[:200]}")
r = requests.post(V + f"/comments/{C2}/choice", headers=FT, json={"choice_ids": ["no"]})
check(r.ok, f"v1 comment: No without proof ok {r.status_code} {r.text[:200]}")
sys.exit(done("p6623_desc_proof"))
