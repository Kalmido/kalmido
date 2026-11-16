#!/usr/bin/env python3
# kalmido-suite: fresh
# freelancer-matrix: office
"""2.1253.0 (#6292, audit #4741 Z3-F1/F2/F3): office rights of the entertainment receipts' payment proposals, the ledger's
files and closing, and the core's role on the office kinds of the level "own". Invented names, companies and figures only.
 - bob (office group "Project management": meals edit, bank / cash book / cards none) gets no bank or cash line offered for
   his meal, may not link one (403) and sees the linked line without its text; erin ("Bookkeeping": bank and cash book)
   and alice (the organisation admin) get both offered
 - carol ("Read-only", no special) gets 403 on the ledger's journal CSV, its PDF and the year-end closing; erin (special
   export) downloads the journal
 - dave ("Staff": meals / travel own): the core's links of somebody else's meal and trip are closed to him (403/404), his own
   meal's links open (200), and he cannot link his meal with alice's
 - a person without an organisation: the bank line offered for her meal, the journal CSV downloads
usage: p21253_6292_officerights_test.py <datadir>   (KMT_NOSTART=1: against a running instance on KALMIDO_TEST_PORT)"""
import os
import subprocess
import sys
import time

import testclock

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
from kt import check, done, sess  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
FEAT = "cal,comments,collab,office,clients,docs,files,travel"
OF = "/api/office"
Y = testclock.today().year - 1

if not os.environ.get("KMT_NOSTART"):
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    time.sleep(0.8)
assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True, "modules": ["cal", "comments"]})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha Example", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done", "workspace": f"org:{ORG}"})  # the rights page works in the org
U = {}
for name, grp in (("bob", "projects"), ("carol", "readonly"), ("dave", "staff"), ("erin", "bookkeeping")):
    r = A.post(B + "/api/users", json={"orgs": [{"id": ORG, "role": "member"}], "username": name, "display_name": name.title(),
                                       "password": "password123", "email": f"{name}@example.com"})
    assert r.ok, r.text
    U[name] = (r.json()["id"], sess(name))
    U[name][1].patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done", "workspace": f"org:{ORG}"})
    r = A.put(B + f"{OF}/rights/people/{U[name][0]}", json={"groups": [f"tpl:{grp}"]})
    check(r.ok, f"setup: {name} in the office group {grp} ({r.status_code} {r.text[:200]})")
BOB, Bo = U["bob"]
Ca, De, Er = U["carol"][1], U["dave"][1], U["erin"][1]


def camt(entries):
    return ('<?xml version="1.0" encoding="UTF-8"?><Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt><Stmt><Id>S</Id>'
            '<Acct><Id><IBAN>DE02120300000000202051</IBAN></Id><Ccy>EUR</Ccy></Acct>' + "".join(entries) + '</Stmt></BkToCstmrStmt></Document>')


def ntry(amt, day, ref):
    return (f'<Ntry><Amt Ccy="EUR">{amt}</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts><BookgDt><Dt>{day}</Dt></BookgDt><AcctSvcrRef>{ref}</AcctSvcrRef>'
            f'<NtryDtls><TxDtls><RltdPties><Cdtr><Pty><Nm>Trattoria {ref}</Nm></Pty></Cdtr></RltdPties><RmtInf><Ustrd>Buchung {ref}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>')


def meal(host, day):
    return {"date": day, "place_name": "Trattoria Esempio", "place_address": "Beispielweg 1\n12345 Musterstadt",
            "occasion": "Negotiation of the follow-up order", "host": {"id": host},
            "guests": [{"name": "Gina Gast", "extra": "Example GmbH, buyer"}],
            "amounts": [{"kind": "food", "rate": 19, "gross": "119.00"}, {"kind": "drinks", "rate": 7, "gross": "21.40"}], "tip": "10"}


def books(s, who):
    """The office's master data, a bank line of the meal's amount and a cash box with money out -> the bank line's id."""
    check(s.put(B + OF + "/settings", json={"lang": "de", "currency": "EUR",
                                           "company_fields": {"name": f"{who} Beispiel GmbH", "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt",
                                                              "country": "DE", "tax_number": "12/345/67890", "iban": "DE02120300000000202051"}}).ok, f"{who}: office settings")
    r = s.post(B + OF + "/bank/import", json={"text": camt([ntry("150.40", f"{Y}-09-10", "MEAL")]), "filename": "konto.xml"})
    check(r.status_code == 201, f"{who}: bank import {r.status_code} {r.text[:200]}")
    tx = {t["purpose"].split()[-1]: t["id"] for t in s.get(B + OF + "/bank/tx?state=all").json()["items"]}
    r = s.post(B + OF + "/cashbooks", json={"name": "Handkasse", "opening": "100.00", "opening_day": f"{Y}-01-01"})
    check(r.status_code == 201, f"{who}: a cash box {r.text[:200]}")
    r = s.post(B + OF + f"/cashbooks/{r.json()['id']}/entries", json={"day": f"{Y}-09-09", "dir": "out", "amount": "20.00", "text": "Kaffee Beispiel"})
    check(r.status_code == 201, f"{who}: cash out {r.text[:200]}")
    check(s.put(B + OF + "/books/ledger/settings", json={"method": "balance", "size": "small"}).ok, f"{who}: double-entry ledger on")
    return tx["MEAL"]


def kinds(p):
    return sorted({x["kind"] for x in p.get("candidates", [])})


# ---------------------------------------------------------------- (1) the meal's payment proposals by source right
TX = books(A, "alice")
r = Bo.post(B + OF + "/meals", json=meal(BOB, f"{Y}-09-08"))
check(r.status_code == 201, f"setup: bob enters his meal {r.text[:200]}")
MID = r.json()["id"]
p = A.get(B + f"{OF}/meals/{MID}/payment").json()
check(kinds(p) == ["bank", "cash"], f"alice (admin): bank and cash offered {kinds(p)}")
p = Er.get(B + f"{OF}/meals/{MID}/payment").json()
check(kinds(p) == ["bank", "cash"], f"erin (bookkeeping: bank + cash book): bank and cash offered {kinds(p)}")
r = Bo.get(B + f"{OF}/meals/{MID}/payment")
check(r.ok and r.json()["candidates"] == [], f"#6292 bob (meals edit, no bank / cash book / cards): nothing offered {r.status_code} {r.text[:300]}")
r = Bo.put(B + f"{OF}/meals/{MID}/payment", json={"kind": "bank", "id": TX})
check(r.status_code == 403, f"#6292 bob: may not link a bank line (403) {r.status_code} {r.text[:200]}")
r = A.put(B + f"{OF}/meals/{MID}/payment", json={"kind": "bank", "id": TX})
check(r.ok and r.json()["current"]["text"], f"alice links the bank line, with its text {r.text[:200]}")
r = Bo.get(B + f"{OF}/meals/{MID}/payment?candidates=0")
cur = r.json().get("current") if r.ok else None
check(cur and cur["amount"] == "150.40" and cur["text"] == "", f"#6292 bob: the linked line without its text {r.status_code} {cur}")
r = Bo.put(B + f"{OF}/meals/{MID}/payment", json={"kind": None})
check(r.status_code == 403, f"#6292 review: bob may not take the bookkeeping's bank link off ({r.status_code})")
r = Bo.put(B + f"{OF}/meals/{MID}/payment", json={"kind": "bank", "id": 99999999})
check(r.status_code == 403, f"#6292 review: bob gets 403 (not 404) for a bank id that does not exist ({r.status_code})")
check(A.put(B + f"{OF}/meals/{MID}/payment", json={"kind": None}).ok, "alice takes the link off")

# ---------------------------------------------------------------- (2) the ledger's files and closing need their specials
L = OF + "/books/ledger"
check(A.get(B + f"{L}/journal.csv?year={Y}").status_code == 200, "alice: the journal CSV")
check(Er.get(B + f"{L}/journal.csv?year={Y}").status_code == 200, "erin (special export): the journal CSV")
check(Ca.get(B + f"{L}?year={Y}").status_code == 200, "carol (read-only): the ledger page itself")
for path in (f"{L}/journal.csv?year={Y}", f"{L}/susa.csv?year={Y}", f"{L}/bs.pdf?year={Y}"):
    r = Ca.get(B + path)
    check(r.status_code == 403, f"#6292 carol (no special export): {path} 403 ({r.status_code})")
r = Ca.post(B + f"{L}/close", json={"year": Y})
check(r.status_code == 403, f"#6292 carol (no special lock): the year-end closing 403 ({r.status_code})")

# ---------------------------------------------------------------- (3) the core's links of the "own" kinds
r = A.post(B + OF + "/meals", json=meal(ALICE, f"{Y}-10-01"))
check(r.status_code == 201, f"setup: alice's meal {r.text[:200]}")
AMID = r.json()["id"]
r = De.post(B + OF + "/meals", json=meal(U["dave"][0], f"{Y}-10-02"))
check(r.status_code == 201, f"setup: dave's own meal {r.text[:200]}")
DMID = r.json()["id"]
TD = f"{Y}-10-05"
r = A.post(B + OF + "/trips", json={"date_from": TD, "date_to": TD, "dest": "Hamburg", "country": "DE",
                                   "items": [{"date": TD, "category": "train", "amount": "40.00", "currency": "EUR"}]})
check(r.status_code == 201, f"setup: alice's trip {r.text[:200]}")
ATID = r.json()["id"]
check(De.get(B + f"/api/obj/omeal/{DMID}/links").status_code == 200, "dave: the links of his own meal (200)")
r = De.get(B + f"/api/obj/omeal/{AMID}/links")
check(r.status_code in (403, 404), f"#6292 dave (meals own): alice's meal's links closed ({r.status_code})")
r = De.get(B + f"/api/obj/otrip/{ATID}/links")
check(r.status_code in (403, 404), f"#6292 dave (travel own): alice's trip's links closed ({r.status_code})")
r = De.post(B + f"/api/obj/omeal/{DMID}/links", json={"kind": "omeal", "id": AMID, "note": "probe"})
check(r.status_code in (403, 404), f"#6292 dave: no link from his meal to alice's ({r.status_code} {r.text[:200]})")
check(A.get(B + f"/api/obj/omeal/{DMID}/links").status_code == 200, "alice (admin) still reads the links of dave's meal")
check(Ca.get(B + f"/api/obj/omeal/{AMID}/links").status_code == 200, "carol (read-only: meals view) reads the links of alice's meal")
r = Ca.post(B + f"/api/obj/omeal/{AMID}/links", json={"kind": "otrip", "id": ATID, "note": "probe"})
check(r.status_code in (403, 404), f"#6292 review: carol (read-only) links nothing to alice's meal ({r.status_code} {r.text[:200]})")

# ---------------------------------------------------------------- a person without an organisation (freelancer-matrix: office)
_, F = freelancer(B, A, features=FEAT)
FTX = books(F, "frida")
me = F.get(B + "/api/state").json()["me"]["id"]
r = F.post(B + OF + "/meals", json=meal(me, f"{Y}-09-08"))
check(r.status_code == 201, f"frida: her meal {r.text[:200]}")
p = F.get(B + f"{OF}/meals/{r.json()['id']}/payment").json()
check(kinds(p) == ["bank", "cash"] and any(x["id"] == FTX for x in p["candidates"]), f"frida (no organisation): bank and cash offered {p}")
check(F.get(B + f"{L}/journal.csv?year={Y}").status_code == 200, "frida: her journal CSV")
check(F.get(B + f"/api/obj/omeal/{r.json()['id']}/links").status_code == 200, "frida: the links of her own meal")
sys.exit(done("p21253_6292_officerights"))
