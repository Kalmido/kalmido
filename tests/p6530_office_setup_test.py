#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1416.0 (#6530): a quotation needs its sender, the company name is preset from the organisation, own container (start.sh).
Invented companies and people only. freelancer-matrix: office
Played in an organisation's office and in the personal office of a person without an organisation:
 - a quotation of an office without a company address cannot be finalised (400 names "company address"; the personal office
   also "company name"), the draft lists the same blocks in GET (missing, #6529); nothing is numbered or locked
 - the organisation's office has its company name preset from the organisation's name (settings company_fields.name, the
   printed sender); the personal office stays without one (no guess from the account's display name)
 - with name and address the quotation finalises (no tax number, bank or period needed for a quotation)
 - the setting of dismissed office hints takes "<office>:setup" (the card "Set up your office"), nothing else new
usage: p6530_office_setup_test.py <datadir>      (P6530_NOSTART=1: a running server on KALMIDO_TEST_PORT, no start.sh)"""
import json
import os
import subprocess
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
OFF = "/api/office"
D = OFF + "/docs"
FEAT = "cal,comments,collab,office,clients"

if os.environ.get("P6530_NOSTART") != "1":
    subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], check=True, stdout=subprocess.DEVNULL)
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Nordlicht Film GmbH", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A, "erin")  # freelancer-matrix: office (the personal office, its own admin)


def err(r):
    try:
        return r.json().get("error", "")
    except ValueError:
        return r.text


def blocks(doc):
    return [m["key"] for m in doc.get("missing") or [] if m.get("level") == "block"]


def run(who, s, personal):
    st = s.get(B + OFF + "/settings").json()
    name = (st.get("company_fields") or {}).get("name") or ""
    if personal:
        check(name == "", f"{who}: no company name guessed for a personal office {name!r}")
    else:
        check(name == "Nordlicht Film GmbH", f"{who}: the company name is preset from the organisation {name!r}")
    r = s.post(B + D, json={"kind": "offer", "lang": "en", "project_title": "Imagefilm", "items": [{"title": "Konzept", "qty": 1, "rate": 800}]})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    d = s.get(B + f"{D}/{did}").json()
    want = (["company_name"] if personal else []) + ["company_address"]
    check(blocks(d) == want, f"{who}: the draft lists only its sender {blocks(d)} (want {want})")
    r = s.post(B + f"{D}/{did}/finalize")
    check(r.status_code == 400 and "company address" in err(r), f"{who}: a quotation without the address is refused {r.status_code} {err(r)[:160]}")
    check(("company name" in err(r)) == personal, f"{who}: the company name {'named' if personal else 'not named (preset)'}: {err(r)[:160]}")
    d = s.get(B + f"{D}/{did}").json()
    check(not d.get("locked") and d["status"] == "draft", f"{who}: still an unlocked draft")
    check(s.put(B + OFF + "/settings", json={"company_fields": {"name": f"Studio {who}", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE"}}).ok,
          f"{who}: name and address (no tax number, no bank)")
    check(blocks(s.get(B + f"{D}/{did}").json()) == [], f"{who}: nothing blocks any more")
    r = s.post(B + f"{D}/{did}/finalize")
    check(r.ok and r.json().get("locked"), f"{who}: finalised with name and address {r.status_code} {r.text[:200]}")
    # the card "Set up your office" is hidden with the existing setting of dismissed office hints
    oid = st.get("org_id")
    r = s.patch(B + "/api/settings", json={"set_delta": {"trial_hint_seen": {"add": [f"{oid}:setup"]}}})
    check(r.ok and f"{oid}:setup" in json.loads(s.get(B + "/api/state").json()["settings"]["trial_hint_seen"]), f"{who}: '<office>:setup' is kept {r.status_code} {r.text[:160]}")
    r = s.patch(B + "/api/settings", json={"set_delta": {"trial_hint_seen": {"add": [f"{oid}:other"]}}})
    check(r.status_code == 400, f"{who}: another word is refused {r.status_code}")


run("org", A, False)
run("freelancer", Fr, True)
print(f"p6530_office_setup: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
