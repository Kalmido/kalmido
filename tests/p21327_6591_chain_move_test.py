#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1327.0 (#6591) API test, own container: the hash chain when a personal office moves into an organisation, and billed
time when a project changes its workspace. Invented people, companies and figures only (example.com).
freelancer-matrix: office  tenant-matrix: office
 - a person without an organisation fills the personal office (two finalised invoices), then moves it into an organisation
   she administers that has two finalised invoices of its own: the documents join the organisation's chain after its own
   (in the order they were finalised, places 3 and 4, no two documents on one place), the organisation's chain check is
   intact with four documents and nothing pending -- in the answer of the move and in GET /api/office/log/chain; each moved
   invoice has the office log line "chain_moved"; the log of the move notes the personal office's own check before
 - 2.1386.0 (#6882): before that, one of the personal office's invoices changed in the database: the preview names it as a
   conflict and the move refuses (409, its number named) -- nothing moved, nothing chained anew
 - a project of the organisation with two time entries, one billed on the organisation's finalised invoice (which names
   the project): the project goes into the private workspace -> the billed entry no longer points at that invoice but stays
   billed ("billed in an earlier organisation": billed_at kept, not billable; GET shows billed with earlier, a change of
   its duration 409, the note still changes), the open one stays open; the invoice no longer names the project
 - 2.1386.0 (#6934 F1): a third entry billed on a draft of the organisation (its position names the project) is free again
   after the project moved (billed_doc_id / billed_at NULL, billable, its duration changes), the position lets go of the project
usage: p21327_6591_chain_move_test.py <datadir>"""
import base64
import os
import sys

import kt
from kt import B, check

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbx as dbxm  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402

kt.docker_logs_on_first_fail()
DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
KEY = base64.b64encode(os.urandom(32)).decode()
OFC = "/api/office"
FEAT = "cal,comments,collab,office,clients,docs,time"
COMPANY = {"name": "Frida Film", "street": "Teststrasse 1", "zip": "20000", "city": "Hamburg", "country": "DE",
           "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001"}


def sql(q, args=(), write=False):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(q, args)
        if write:
            c.commit()
            return None
        return r.fetchall()
    finally:
        c.close()


def ws(s, v):
    r = s.patch(B + "/api/settings", json={"workspace": v})
    assert r.ok, r.text


def invoice(s, title, list_id=None):
    r = s.post(B + "/api/clients", json={"name": "Example Client Ltd " + title, "street": "Marktstrasse 5", "zip": "50000", "city": "Koeln", "country": "DE"})
    assert r.ok, r.text
    b = {"kind": "invoice", "client_id": r.json()["id"], "service_from": "2026-03-01", "service_to": "2026-03-02",
         "items": [{"title": title, "qty": 1, "rate": 120}]}
    r = s.post(B + OFC + "/docs", json=b)
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    r = s.post(B + OFC + f"/docs/{did}/finalize")
    assert r.ok, r.text
    if list_id:  # the project of the document (also on a finalised one, docproject.py)
        r = s.post(B + OFC + f"/docs/{did}/project", json={"list_id": list_id})
        assert r.ok, r.text
    return did


def chain(did):
    return sql("SELECT org_id, chain_key, chain_seq FROM office_docs WHERE id=?", (did,))[0]


kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ORGCRYPT_DELAY": "0", "KALMIDO_SECRET_KEY": KEY}, data=DATA)
A = kt.setup()

# ---------------------------------------------------------------- the personal office: two finalised invoices  # freelancer-matrix: office
FID, Fr = freelancer(B, A, "frida", features=FEAT)
ws(Fr, "private")
assert Fr.put(B + OFC + "/settings", json={"company_fields": COMPANY}).ok
P1, P2 = invoice(Fr, "Schnitt"), invoice(Fr, "Farbe")
PB = sql("SELECT id FROM orgs WHERE personal_of=?", (FID,))[0][0]
check(chain(P1)[2] == 1 and chain(P2)[2] == 2, f"setup: the personal office's chain {chain(P1)} {chain(P2)}")

# ---------------------------------------------------------------- the organisation with its own chain  # tenant-matrix: office
ALPHA = A.post(B + "/api/admin/orgs", json={"name": "Alpha Studio", "admin_id": FID}).json()["id"]
# its numbers far from the personal office's (a number twice refuses the move, p2137_d): the counters of the same series at 50
for kind, period in sql("SELECT kind, period FROM office_numbers WHERE org_id=?", (PB,)):
    sql("INSERT INTO office_numbers(org_id, kind, period, last) VALUES(?,?,?,50)", (ALPHA, kind, period), write=True)
ws(Fr, f"org:{ALPHA}")
assert Fr.put(B + OFC + "/settings", json={"company_fields": dict(COMPANY, name="Alpha Studio GmbH")}).ok
r = Fr.post(B + "/api/lists", json={"name": "Werbespot", "org_id": ALPHA})
assert r.ok, r.text
LID = r.json()["id"]
A1, A2 = invoice(Fr, "Dreh", list_id=LID), invoice(Fr, "Ton")
check([chain(A1)[2], chain(A2)[2]] == [1, 2] and chain(A1)[1] == chain(P1)[1], f"setup: the organisation's own chain, the same series {chain(A1)} {chain(P1)}")
k = Fr.get(B + OFC + "/log/chain").json()
check(k.get("ok") is True and k.get("count") == 2, f"setup: the organisation's chain intact {k}")

# ---------------------------------------------------------------- b) the project leaves the organisation: billed time
r = Fr.post(B + "/api/time/entries", json={"list_id": LID, "start": "2026-03-01T09:00", "minutes": 60, "note": "Dreh"})
assert r.ok, r.text
TB = r.json()["id"]
r = Fr.post(B + "/api/time/entries", json={"list_id": LID, "start": "2026-03-02T09:00", "minutes": 30, "note": "Schnitt"})
assert r.ok, r.text
TO = r.json()["id"]
sql("UPDATE time_entries SET billed_doc_id=?, billed_at='2026-03-05T10:00:00+00:00' WHERE id=?", (A1, TB), write=True)  # as "invoice from time" did
check(sql("SELECT list_id FROM office_docs WHERE id=?", (A1,)) == [(LID,)], "setup: the invoice names the project")
# 2.1386.0 (#6934 F1): a third entry on a draft of the organisation (its position names the project): never billed
r = Fr.post(B + "/api/time/entries", json={"list_id": LID, "start": "2026-03-03T09:00", "minutes": 45, "note": "Farbe"})
assert r.ok, r.text
TD = r.json()["id"]
r = Fr.post(B + OFC + "/docs", json={"kind": "invoice", "client_id": sql("SELECT client_id FROM office_docs WHERE id=?", (A1,))[0][0],
                                     "items": [{"title": "Farbe", "qty": 0.75, "rate": 120}]})
assert r.status_code == 201, r.text
AD = r.json()["id"]
ADI = sql("SELECT id FROM office_doc_items WHERE doc_id=? ORDER BY id LIMIT 1", (AD,))[0][0]
sql("UPDATE office_doc_items SET list_id=? WHERE id=?", (LID, ADI), write=True)
sql("UPDATE time_entries SET billed_doc_id=?, billed_item_id=?, billed_at='2026-03-05T11:00:00+00:00' WHERE id=?", (AD, ADI, TD), write=True)
check(sql("SELECT locked_at FROM office_docs WHERE id=?", (AD,)) == [(None,)], "setup: a draft")
r = Fr.patch(B + f"/api/lists/{LID}", json={"org_id": None})
check(r.ok and sql("SELECT org_id FROM lists WHERE id=?", (LID,)) == [(None,)], f"the project goes into the private workspace {r.status_code} {r.text[:200]}")
row = sql("SELECT billed_doc_id, billed_item_id, billable, billed_at IS NOT NULL FROM time_entries WHERE id=?", (TB,))
check(row == [(None, None, False, True)], f"#6591: the billed entry no longer points at the organisation's invoice, stays billed (not billable, its day kept) {row}")
check(sql("SELECT billed_doc_id, billable, billed_at FROM time_entries WHERE id=?", (TO,)) == [(None, True, None)], "#6591: the open entry stays open")
e = Fr.get(B + f"/api/time/entries/{TB}").json()
check((e.get("billed") or {}).get("earlier") is True and (e.get("billed") or {}).get("id") is None, f"#6591: shown as billed in an earlier organisation {e.get('billed')}")
r = Fr.patch(B + f"/api/time/entries/{TB}", json={"minutes": 90})
check(r.status_code == 409 and sql("SELECT seconds FROM time_entries WHERE id=?", (TB,)) == [(3600,)], f"#6591: its duration stays locked {r.status_code}")
r = Fr.patch(B + f"/api/time/entries/{TB}", json={"note": "Dreh, Tag 1"})
check(r.ok, f"#6591: its note still changes {r.status_code} {r.text[:200]}")
check(sql("SELECT list_id FROM office_docs WHERE id=?", (A1,)) == [(None,)] and not sql("SELECT 1 FROM office_doc_items WHERE doc_id=? AND list_id=?", (A1, LID)),
      "#6591: the organisation's invoice no longer names the project")
row = sql("SELECT billed_doc_id, billed_item_id, billable, billed_at FROM time_entries WHERE id=?", (TD,))
check(row == [(None, None, True, None)], f"#6934: the entry on the draft is free again (billable, not 'billed earlier') {row}")
e = Fr.get(B + f"/api/time/entries/{TD}").json()
check(not e.get("billed"), f"#6934: shown as not billed {e.get('billed')}")
r = Fr.patch(B + f"/api/time/entries/{TD}", json={"minutes": 50})
check(r.ok, f"#6934: its duration changes again {r.status_code} {r.text[:200]}")
check(not sql("SELECT 1 FROM office_doc_items WHERE id=? AND list_id IS NOT NULL", (ADI,)), "#6934: the draft's position let go of the project")

# ---------------------------------------------------------------- 2.1386.0 (#6882): a broken chain refuses the move
ws(Fr, "private")
dt = sql("SELECT date FROM office_docs WHERE id=?", (P2,))[0][0]
sql("UPDATE office_docs SET date=? WHERE id=?", ("2026-01-02" if str(dt) != "2026-01-02" else "2026-01-03", P2), write=True)  # changed in the database
NO2 = sql("SELECT number FROM office_docs WHERE id=?", (P2,))[0][0]
r = Fr.get(B + OFC + f"/move/check?org={ALPHA}")
pv = r.json() if r.ok else {}
check(pv.get("ok") is False and any(NO2 in x for x in pv.get("conflicts") or []),
      f"#6882: the preview names the broken document of the personal office as a conflict {r.status_code} {r.text[:300]}")
r = Fr.post(B + OFC + "/move/org", json={"org": ALPHA, "confirm": True})
check(r.status_code == 409 and NO2 in r.text, f"#6882: the move refuses (409) and names the document {r.status_code} {r.text[:300]}")
check(chain(P1)[0] == PB and chain(P2)[0] == PB and [chain(P1)[2], chain(P2)[2]] == [1, 2] and chain(A2)[2] == 2,
      f"#6882: nothing moved, nothing chained anew {[chain(x) for x in (P1, P2, A2)]}")
sql("UPDATE office_docs SET date=? WHERE id=?", (dt, P2), write=True)  # taken back: intact again

# ---------------------------------------------------------------- a) the personal office moves into the organisation
r = Fr.get(B + OFC + f"/move/check?org={ALPHA}")
check(r.ok and r.json().get("ok") is True, f"setup: the preview has no conflict {r.text[:300]}")
r = Fr.post(B + OFC + "/move/org", json={"org": ALPHA, "confirm": True})
j = r.json() if r.ok else {}
ch = j.get("chain") or {}
check(r.ok and ch.get("ok") is True and ch.get("count") == 4 and ch.get("pending") == 0 and ch.get("first_bad") is None,
      f"#6591: the answer of the move carries the organisation's intact chain (4 documents) {r.status_code} {r.text[:300]}")
check([chain(x) for x in (A1, A2, P1, P2)] == [(ALPHA, chain(A1)[1], n) for n in (1, 2, 3, 4)],
      f"#6591: the moved invoices joined after the organisation's own, in the order they were finalised {[chain(x) for x in (A1, A2, P1, P2)]}")
check(sql("SELECT COUNT(*) FROM (SELECT chain_key, chain_seq FROM office_docs WHERE org_id=? AND chain_seq IS NOT NULL GROUP BY 1, 2 HAVING COUNT(*) > 1) x",
          (ALPHA,))[0][0] == 0, "#6591: no two documents on one place")
ws(Fr, f"org:{ALPHA}")
k = Fr.get(B + OFC + "/log/chain").json()
check(k.get("ok") is True and k.get("count") == 4 and k.get("pending") == 0, f"#6591: GET /api/office/log/chain intact afterwards {k}")
check(sorted(x[0] for x in sql("SELECT doc_id FROM office_doc_log WHERE org_id=? AND action='chain_moved'", (ALPHA,))) == sorted((P1, P2)),
      "#6591: one log line 'chain_moved' per moved invoice")
mv = sql("SELECT detail FROM office_doc_log WHERE org_id=? AND action='move' ORDER BY id DESC LIMIT 1", (ALPHA,))
check(bool(mv) and '"chain_before"' in str(mv[0][0]) and '"ok": true' in str(mv[0][0]).replace('":true', '": true'),
      f"#6591: the log of the move notes the personal office's own check before {str(mv)[:300]}")

sys.exit(kt.done("p21327_6591_chain_move"))
