#!/usr/bin/env python3
# kalmido-suite: fresh
"""#7313 (package 2.1465 part C): every office request names its area; the server never guesses an office.
Invented companies and figures only.
 - a person in two organisations (Alpha, Beta) under "All workspaces": without a named area 400 office_no_area; the area the
   request names wins under every workspace (F1), also when the saved setting says another one (a failed / overtaken PATCH,
   another tab switched meanwhile): a quotation made with the header Beta lands in Beta's office (a, b)
 - the calls from outside the office (F12) answer 200 for the office named: figures, settings read and write, the search
 - an object's number (a quotation) opens in its own office, with another area named or none; the answer names it
   (X-Kalmido-Office-Area, F13)
 - the two ways of #7297: under "All" with only one office on (own office and Beta off for me) that one opens without a
   header; the workspace chosen at the top (setting org:Alpha) opens Alpha's office
 - F17: a guest of the only organisation (own office on) gets their own office, never 403 of the organisation's; an
   organisation whose office I switched off is never chosen
 - F16: leaving an organisation resets the setting org:<id> to "All"; meanwhile a stale setting counts as "All"
 - freelancer-matrix: office (a person without an organisation: their own office under "All", nothing to choose)
usage: p21465_c_office_area_test.py <datadir>"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kt  # noqa: E402
from kt import B, FAILS, OKS, check, sess  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

HS, HA = "X-Kalmido-Office-Space", "X-Kalmido-Office-Area"
OF = "/api/office"
FEAT = "cal,comments,collab,clients,office,docs,files,contacts"
if not kt.nostart("P21448C"):
    subprocess.run(["rm", "-rf", kt.DATA])
    kt.fresh(prefix="P21448C")
A = kt.setup()
ALICE = A.get(B + "/api/state").json()["me"]["id"]
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALPHA = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
BETA = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": ALICE}).json()["id"]
for oid, name in ((ALPHA, "Alpha Studio GmbH"), (BETA, "Beta Werkstatt GmbH")):
    r = A.put(B + OF + "/settings", json={"company_fields": {"name": name, "country": "de"}, "lang": "en", "currency": "EUR"},
              headers={HS: f"org:{oid}"})
    check(r.ok, f"setup: the office of {name} " + r.text[:160])
A.patch(B + "/api/settings", json={"workspace": "all"})


def where(s, sp=None):
    r = s.get(B + OF + "/settings", headers={HS: sp} if sp else {})
    try:
        j = r.json()
    except ValueError:
        j = {}
    return r.status_code, j.get("org_id"), bool(j.get("personal")), r.headers.get(HA), (j.get("code") if not r.ok else None)


def ws(s):
    return s.get(B + "/api/state").json()["settings"].get("workspace") or "all"


# ---------------------------------------------------------------- F1 / no guess
st = where(A)
check(st[0] == 400 and st[4] == "office_no_area", f"All, two organisations, nothing named: 400 office_no_area {st}")
check(where(A, f"org:{BETA}")[:2] == (200, BETA) and where(A, f"org:{BETA}")[3] == f"org:{BETA}",
      f"the named area: its office, the answer names it {where(A, f'org:{BETA}')}")
A.patch(B + "/api/settings", json={"workspace": f"org:{ALPHA}"})
check(where(A, f"org:{BETA}")[:2] == (200, BETA), "F1: the setting says Alpha, the request names Beta: Beta")
check(where(A)[:2] == (200, ALPHA), "without a header the setting is the default (tokens, old clients)")

# (a) the PATCH of the setting failed / was overtaken: the server still holds Alpha, the page shows Beta and makes a quotation
r = A.post(B + OF + "/docs", json={"project_title": "Angebot Beta"}, headers={HS: f"org:{BETA}"})
check(r.status_code in (200, 201), f"(a) a quotation made in the office shown (Beta) {r.status_code} {r.text[:160]}")
DOC = r.json().get("id")
row = kt.dbx("SELECT org_id FROM office_docs WHERE id=?", (DOC,))
check(row and row[0][0] == BETA, f"(a) it landed in Beta's office, not in the saved Alpha {row}")
# (b) a second tab switches the setting to Alpha meanwhile; the first tab (Beta shown) makes another one
A.patch(B + "/api/settings", json={"workspace": f"org:{ALPHA}"})
r = A.post(B + OF + "/docs", json={"project_title": "Angebot Beta 2"}, headers={HS: f"org:{BETA}"})
row = kt.dbx("SELECT org_id FROM office_docs WHERE id=?", (r.json().get("id"),)) if r.ok else None
check(row and row[0][0] == BETA, f"(b) another tab chose Alpha: the quotation of the Beta tab lands in Beta {r.status_code} {row}")

# ---------------------------------------------------------------- objects carry their office (F13, late saves)
A.patch(B + "/api/settings", json={"workspace": "all"})
r = A.get(B + OF + f"/docs/{DOC}")
check(r.ok and r.headers.get(HA) == f"org:{BETA}", f"F13: Beta's quotation without an area under All: opens, named Beta {r.status_code} {r.headers.get(HA)}")
r = A.get(B + OF + f"/docs/{DOC}", headers={HS: f"org:{ALPHA}"})
check(r.ok and r.headers.get(HA) == f"org:{BETA}", f"a save / read sent late with Alpha named: the object's own office Beta {r.status_code}")
r = A.patch(B + OF + f"/docs/{DOC}", json={"project_title": "Angebot Beta neu"}, headers={HS: f"org:{ALPHA}"})
check(r.ok, f"the delayed save after a switch to Alpha lands on Beta's quotation {r.status_code} {r.text[:160]}")
check(A.get(B + OF + f"/docs/{DOC}", headers={HS: "org:999999"}).status_code == 400, "a foreign area named: still 400")

# ---------------------------------------------------------------- (d) F12: the calls from outside the office, under All
for path in ("/kpi", "/settings"):
    r = A.get(B + OF + path, headers={HS: f"org:{BETA}"})
    check(r.status_code == 200, f"(d) GET {path} under All with Beta named: 200 ({r.status_code} {r.text[:120]})")
r = A.put(B + OF + "/settings", json={"company_fields": {"name": "Beta Werkstatt Kassel GmbH", "country": "de"}}, headers={HS: f"org:{BETA}"})
check(r.ok and where(A, f"org:{ALPHA}")[0] == 200, f"(d) Settings > Company & office writes Beta's office {r.status_code}")


def coname(sp):
    return (A.get(B + OF + "/settings", headers={HS: sp}).json().get("company_fields") or {}).get("name")


check(coname(f"org:{BETA}") == "Beta Werkstatt Kassel GmbH" and coname(f"org:{ALPHA}") == "Alpha Studio GmbH",
      f"(d) only Beta changed {coname(f'org:{BETA}')} {coname(f'org:{ALPHA}')}")
cl = A.post(B + "/api/clients", json={"name": "Example Kunde Beta", "org_id": BETA})
check(cl.status_code == 201, "setup: a client of Beta " + cl.text[:120])
r = A.get(B + "/api/search", params={"q": "Example Kunde"}, headers={HS: f"org:{BETA}"})
hits = json.dumps(r.json()) if r.ok else ""
check(r.ok and "Example Kunde Beta" in hits, f"(d) the search under All with Beta named finds Beta's client {r.status_code}")

# ---------------------------------------------------------------- the two ways of #7297
A.patch(B + "/api/settings", json={"workspace": "all", "ws_mods_off": json.dumps({"private": ["office"], f"org:{BETA}": ["office"]})})
st = where(A)
check(st[:2] == (200, ALPHA), f"under All with only Alpha's office on: it opens without a header {st}")
A.patch(B + "/api/settings", json={"workspace": f"org:{ALPHA}", "ws_mods_off": "{}"})
check(where(A)[:2] == (200, ALPHA) and where(A, f"org:{ALPHA}")[:2] == (200, ALPHA), "the workspace Alpha chosen at the top: Alpha's office")
A.patch(B + "/api/settings", json={"workspace": "all"})

# ---------------------------------------------------------------- F17: never a guest's / a switched-off office
r = A.post(B + "/api/users", json={"orgs": [{"id": ALPHA, "role": "guest"}], "username": "gustav", "display_name": "Gustav",
                                   "password": "password123", "email": "gustav@example.com"})
check(r.ok, "setup: gustav, guest of Alpha " + r.text[:160])
G = sess("gustav")
G.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEAT, "workspace": "all"})
st = where(G)
check(st[0] == 200 and st[2], f"F17: a guest of the only organisation under All: their own office, not Alpha's 403 {st}")
r = A.post(B + "/api/users", json={"orgs": [{"id": ALPHA, "role": "member"}], "username": "mira", "display_name": "Mira",
                                   "password": "password123", "email": "mira@example.com"})
M = sess("mira")
M.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEAT, "workspace": "all", "ws_mods_off": json.dumps({f"org:{ALPHA}": ["office"]})})
st = where(M)
check(st[0] == 200 and st[2], f"F17: the office of the only organisation switched off for me: never that one {st}")
M.patch(B + "/api/settings", json={"ws_mods_off": "{}"})
check(where(M)[:2] == (200, ALPHA), f"switched on again: her own office is empty (#2932), Alpha's is the only one {where(M)}")
r = M.post(B + OF + "/docs", json={"project_title": "Eigenes Angebot"}, headers={HS: "private"})
check(r.status_code in (200, 201), f"setup: a quotation in her own office {r.status_code} {r.text[:120]}")
check(where(M)[0] == 400, f"her own office holds data now: two offices on, nothing named = 400 {where(M)}")
M.patch(B + "/api/settings", json={"ws_mods_off": json.dumps({"private": ["office"]})})
check(where(M)[:2] == (200, ALPHA), f"her own office off: the only office on is Alpha's {where(M)}")
M.patch(B + "/api/settings", json={"ws_mods_off": "{}"})

# ---------------------------------------------------------------- F16: leaving resets the setting
M.patch(B + "/api/settings", json={"workspace": f"org:{ALPHA}"})
MIRA = M.get(B + "/api/state").json()["me"]["id"]
r = M.delete(B + f"/api/orgs/{ALPHA}/members/{MIRA}")
check(r.ok, f"setup: mira leaves Alpha {r.status_code} {r.text[:160]}")
check(ws(M) == "all", f"F16: the setting org:Alpha became All on leaving ({ws(M)})")
st = where(M)
check(st[0] == 200 and st[2], f"F16: after leaving her own office, never Alpha's {st}")
check(where(M, f"org:{ALPHA}")[0] == 400, "F16: Alpha named after leaving: 400")

# ---------------------------------------------------------------- freelancer-matrix: office
FID, Fr = freelancer(B, A, "frida", features=FEAT)
Fr.patch(B + "/api/settings", json={"workspace": "all"})
st = where(Fr)
check(st[0] == 200 and st[2], f"freelancer: their own office under All, nothing to choose {st}")
check(where(Fr, "private")[2] and where(Fr, f"org:{ALPHA}")[0] == 400, "freelancer: private = own office; a foreign organisation 400")

print(f"p21465_c_office_area: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
