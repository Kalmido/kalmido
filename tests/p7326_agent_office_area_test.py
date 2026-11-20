#!/usr/bin/env python3
# kalmido-suite: fresh
"""#7326: an agent writes only into an office that is on for the person it works for, and its links name that office.
Own container (kt.fresh, mode workspaces). Invented names only.
freelancer-matrix: office
 - a person in an organisation with an own office (Frida) and her personal agent (switch office_drafts, privacy switch
   agents_read, scope office): the agent's quotation and letter drafts land in her own office; the answer's app_url and the
   chat card's link name it (#office/s/private/...), so they open there under any workspace on top (was #office/offers/<id>:
   404 under the organisation)
 - "Also private" off (ws_mods_off "private": ["office"], the switch of Settings > Modules): the agent gets 409 office_off with a
   readable text for drafts and reads alike, nothing is written (was: 201, the draft hidden behind the office's 403); switched
   on again, it drafts as before and the earlier drafts are all there
 - the same person under "All workspaces" and under the organisation: the agent's place does not move (its own workspace)
 - a person without an organisation (P4): her personal agent drafts in her own office as before (the switch is not offered)
usage: p7326_agent_office_area_test.py <datadir>"""
import json
import os
import re
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

V = B + "/api/v1"
OF = "/api/office"
H = {"X-Requested-With": "kalmido"}
HS = "X-Kalmido-Office-Space"
PV = {HS: "private"}
HREF = re.compile(r"^#office/s/private/(offers|letters)/\d+$")


def hd(token):
    return {**H, "Authorization": "Bearer " + token}


def code(r):
    j = r.json() if r.headers.get("Content-Type", "").startswith("application/json") else {}
    e = j.get("error")
    return (e or {}).get("code") if isinstance(e, dict) else None, (e or {}).get("message", "") if isinstance(e, dict) else str(e or "")


def agent(who, s, ws="private"):
    """A personal agent of person s in workspace ws ("private" = her own office; a new agent's default is her first
    organisation) with both office switches of that office -> its token."""
    hs = {HS: ws}
    s.get(B + OF + "/settings", headers=hs)  # opens the office once
    r = s.post(B + "/api/my/agents", json={"username": f"{who}bot", "display_name": f"{who} Bot", "scopes": ["read", "office"],
                                           "org_id": None if ws == "private" else int(ws[4:])})
    check(r.status_code == 201, f"{who}: setup: the personal agent {r.text[:200]}")
    aid, tok = r.json()["id"], r.json()["token"]
    check(s.patch(B + f"{OF}/agents/{aid}", json={"office_drafts": True}, headers=hs).ok and s.put(B + OF + "/settings", json={"agents_read": 1}, headers=hs).ok,
          f"{who}: setup: both office switches of the office {ws}")
    return tok


def offer(tok, cl, title):
    return requests.post(V + "/office/offers", headers=hd(tok), json={"client_id": cl, "title": title, "notify": True,
                                                                       "items": [{"text": "Kamera", "qty": 1, "unit": "day", "price": 500}]})


def own_offers(s):
    r = s.get(B + OF + "/docs?kind=offer", headers=PV)
    return [x["id"] for x in r.json().get("docs", [])] if r.ok else None


def card_href(s, aid_tok, mid):
    """The link of the chat card the draft posted (the person's chat with the agent)."""
    ag = requests.get(V + "/me", headers=hd(aid_tok)).json().get("id")
    r = s.get(B + f"/api/agents/{ag}/chat")
    msgs = r.json().get("messages") or [] if r.ok else []
    m = next((x for x in msgs if x.get("id") == mid), None)
    return next((x.get("href") for x in (m or {}).get("choices") or [] if x.get("id") == "open"), None)


kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces"}, prefix="P7326")
A = kt.setup()
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})

# ---- 1. Frida: an organisation and her own office; her personal agent
FID, Fr = freelancer(B, A)
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha Studio", "admin_id": FID}).json()["id"]
TOK = agent("frida", Fr)
r = Fr.post(B + "/api/clients", json={"name": "Beispiel GmbH", "email": "kunde@example.com", "space": "private"})
check(r.ok, f"setup: a private client {r.status_code} {r.text[:160]}")
CL = r.json().get("id")
for ws in ("all", f"org:{ORG}", "private"):
    check(Fr.patch(B + "/api/settings", json={"workspace": ws}).ok, f"workspace {ws}")
    r = offer(TOK, CL, f"Portrait {ws}")
    j = r.json() if r.ok else {}
    d = j.get("doc") or {}
    check(r.status_code == 201 and d.get("id") in (own_offers(Fr) or []), f"#7326: under {ws} the draft lands in her own office (the agent's own workspace) {r.status_code} {r.text[:160]}")
    check(HREF.match(d.get("app_url") or ""), f"#7326: app_url names the office: {d.get('app_url')!r}")
    if ws == "all" and j.get("chat_message_id"):
        h = card_href(Fr, TOK, j["chat_message_id"])
        check(bool(h) and HREF.match(h), f"#7326: the chat card's link names the office: {h!r}")
r = requests.post(V + "/office/letters", headers=hd(TOK), json={"subject": "Termin", "body": "Guten Tag"})
check(r.status_code == 201 and HREF.match(r.json().get("app_url") or ""), f"#7326: the letter draft's app_url names the office {r.status_code} {r.text[:200]}")
before = own_offers(Fr) or []

# ---- 2. "Also private" off: 409 office_off, nothing written
check(Fr.patch(B + "/api/settings", json={"ws_mods_off": json.dumps({"private": ["office"]})}).ok, "Frida switches the own office off (Also private)")
r = offer(TOK, CL, "Versteckt")
c, msg = code(r)
check(r.status_code == 409 and c == "office_off" and "Also private" in msg, f"#7326: a draft into the office that is off: 409 office_off with a readable text {r.status_code} {r.text[:240]}")
r = requests.get(V + "/office", headers=hd(TOK))
check(r.status_code == 409 and code(r)[0] == "office_off", f"#7326: reading it as well {r.status_code} {r.text[:160]}")
r = requests.post(V + "/office/letters", headers=hd(TOK), json={"subject": "Versteckt", "body": "x"})
check(r.status_code == 409, f"#7326: a letter draft as well {r.status_code}")
check(Fr.patch(B + "/api/settings", json={"ws_mods_off": json.dumps({})}).ok, "Frida switches it on again")
check(own_offers(Fr) == before, f"#7326: nothing was written while off {own_offers(Fr)} vs {before}")
r = offer(TOK, CL, "Wieder an")
check(r.status_code == 201, f"#7326: switched on again, the agent drafts as before {r.status_code} {r.text[:160]}")

# ---- 2b. her personal agent placed in Alpha: drafts in Alpha, the link names Alpha; Alpha's office off for her = 409
WA = f"org:{ORG}"
TOKA = agent("fridaalpha", Fr, WA)
r = Fr.post(B + "/api/clients", json={"name": "Alpha Kunde", "email": "alpha@example.com", "space": WA})
r = offer(TOKA, r.json().get("id"), "Alpha Film")
d = r.json().get("doc") or {} if r.ok else {}
check(r.status_code == 201 and re.match(rf"^#office/s/{WA}/offers/{d.get('id')}$", d.get("app_url") or ""),
      f"#7326: an agent placed in Alpha drafts there, its link names Alpha {r.status_code} {d.get('app_url')!r} {r.text[:160]}")
check(Fr.patch(B + "/api/settings", json={"ws_mods_off": json.dumps({WA: ["office"]})}).ok, "Frida switches the office off in Alpha")
r = offer(TOKA, None, "Alpha versteckt")
check(r.status_code == 409 and code(r)[0] == "office_off", f"#7326: Alpha's office off for her: 409 office_off {r.status_code} {r.text[:200]}")
check(Fr.patch(B + "/api/settings", json={"ws_mods_off": json.dumps({})}).ok, "on again")

# ---- 3. P4: a person without an organisation, her agent as always
FID2, Fi = freelancer(B, A, "fiona")
TOK2 = agent("fiona", Fi)
r = Fi.post(B + "/api/clients", json={"name": "Muster AG", "email": "muster@example.com"})
r = offer(TOK2, r.json().get("id"), "Solo")
check(r.status_code == 201 and HREF.match((r.json().get("doc") or {}).get("app_url") or ""), f"P4: without an organisation the agent drafts in her office {r.status_code} {r.text[:200]}")

sys.exit(kt.done("p7326_agent_office_area"))
