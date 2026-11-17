#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1309.0 part B (#6467, GoBD audit #4791 U1/U2) API tests: the database holds the positions, payments and office log of
finalised documents (core/migrations.d/6467.py), the hash chain has a version 2 with the stored files' checksums and the head
fields (office/chain.py), and the watchdog checks every chain daily. Own container (start.sh), once in an organisation's office
(its admin) and once in the personal office of a person without an organisation (freelancer fixture; freelancer-matrix: office).
Invented companies, people and figures only.
 - refused by the database (a session without the switch kalmido.locked_ok, as the app's connections): a position of a finalised
   invoice changed (title, rate), moved out, a draft's position moved in, a new one added, one deleted; a payment's amount /
   date changed or the payment deleted; an office log entry changed or deleted (not a read entry)
 - goes through: the purchase price of a position, the bank line of a payment (bank_tx_id), the same value written again, a
   draft's positions, a read entry deleted, an agent's log line learning its document once (doc_id from NULL)
 - the ways that keep running: a payment and a credit note through the app, a service deleted for good (service_id emptied),
   a finalised trial document deleted, the prune of read entries (notify/push.py), the one-time name fill of #6470, the trim of
   #2561, an organisation that goes for good (its rows cascade)
 - the chain: a new link has version 2 and covers pdf_sha256 (a changed checksum breaks it, reason data); a link made with
   version 1 stays valid (and does not cover the checksum); hch_heads names the head of every series
 - the watchdog (hch_watch_tick): a new break -> one admin alert and one office log line "chain_broken"; the next day nothing again
 - 2.1333.0 (#6770): an unreadable link no longer hides a later break (the check goes on behind it); found on 3 days in a row
   it gets one admin alert of its own; an office whose check fails (own savepoint) keeps the log line of the office before it
usage: p21309_b_office_gobd_test.py <datadir>      (P21309B_NOSTART=1: a running server on KALMIDO_TEST_PORT)"""
import json
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import CT, DATA, FAILS, OKS, B, H, check, sess, until  # noqa: E402
import requests  # noqa: E402
import testclock  # noqa: E402

OFC = "/api/office"
D = OFC + "/docs"
TODAY = testclock.today().isoformat()
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "tax_number": "12/345/67890", "vat_id": "DE999999999",
           "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}
CLIENT = {"name": "Beispiel Kunde AG", "street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE",
          "email_invoice": "rechnung@kunde.example", "payment_terms_days": 14}
LOCKED = "is finalised"     # the positions' trigger (core/migrations.d/6467.py)
BOOKED = "is booked"        # the payments' trigger
KEPT = "is kept for good"   # the office log's trigger
OLD = "2001-01-01T08:00:00Z"


def free(sql, args=()):
    """The suites' usual access (dbx: past the triggers)."""
    return dbxm.connect(DATA).execute(sql, args)


def guarded(sql, args=()):
    """A statement as the app's connections run it (no switch kalmido.locked_ok) -> "" or the database's error text."""
    try:
        dbxm.connect(DATA, guarded=True).execute(sql, args)
        return ""
    except dbxm.DbError as e:
        return str(e)


def one(sql, args=()):
    r = free(sql, args).fetchone()
    return dict(r) if r else None


def py(code):
    """Runs code in the container (the owner's direct connection c, no switch, under system_ctx) -> the JSON of its last line."""
    src = ("import app, json, sys\nfrom kalmido.core.config import DATABASE_URL\nfrom kalmido.core.db import connect_direct\n"
           "from kalmido.core.pg import system_ctx\nc = connect_direct(DATABASE_URL)\n"
           "with system_ctx(c):\n" + "".join("    " + x + "\n" for x in code.strip().splitlines()) + "c.close()\n")
    out = subprocess.run(["docker", "exec", CT, "python", "-c", src], capture_output=True, text=True)
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"_error": out.stdout[-400:] + out.stderr[-1200:]}


if not os.environ.get("P21309B_NOSTART"):
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
s0 = requests.Session()
s0.headers.update(H)


def _up():
    try:
        return s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"})
    except requests.ConnectionError:
        return None


r = until(_up, 30)  # the server is up once setup answers (a real state, not a fixed time)
assert r is not None and r.ok, r and r.text
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en"})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A)


def run(S, who):
    """The locks and the ways in the office S works in -> (office id, a finalised invoice, the newest finalised invoice)."""
    def ok(cond, what):
        check(cond, f"{who}: {what}")

    r = S.put(B + OFC + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "en", "currency": "EUR", "payment_days": 14,
                                         "company_fields": COMPANY})
    ok(r.ok, "office settings " + r.text[:200])
    r = S.post(B + "/api/clients", json=CLIENT)
    ok(r.status_code in (200, 201), "a client " + r.text[:200])
    cl = r.json().get("id")
    r = S.post(B + OFC + "/services", json={"name_de": "Beratung", "daily_rate": 800})
    ok(r.ok, "a service " + r.text[:200])
    sv = r.json().get("id")

    def doc(final=True, trial=False, title=None):
        r = S.post(B + D, json={"kind": "invoice", "client_id": cl, "project_title": title or f"invoice {who}", "service_from": TODAY,
                                "items": [{"title": "Schnitt", "qty": 1, "rate": 1000}, {"title": "Farbe", "qty": 2, "rate": 250}]})
        ok(r.status_code == 201, "an invoice " + r.text[:200])
        did = r.json()["id"]
        if trial:
            free("UPDATE office_docs SET trial=1 WHERE id=?", (did,))  # a draft: like part A of 2.144.10 sets it
        if final:
            r = S.post(B + f"{D}/{did}/finalize")
            ok(r.ok and r.json().get("locked") is True, f"invoice {did} finalised " + r.text[:200])
        return did

    inv = doc(title="Locked " + who)
    head = one("SELECT org_id, date, pdf_sha256, chain_seq, chain_ver FROM office_docs WHERE id=?", (inv,))
    oid = head["org_id"]
    its = [x["id"] for x in free("SELECT id FROM office_doc_items WHERE doc_id=? ORDER BY sort, id", (inv,)).fetchall()]
    ok(len(its) == 2, f"the invoice has its two positions {its}")
    free("UPDATE office_doc_items SET service_id=? WHERE id=?", (sv, its[0]))
    draft = doc(final=False)
    dits = [x["id"] for x in free("SELECT id FROM office_doc_items WHERE doc_id=? ORDER BY sort, id", (draft,)).fetchall()]
    r = S.post(B + f"{D}/{inv}/payments", json={"date": head["date"], "amount": 100, "method": "transfer"})
    ok(r.ok, "a payment on the finalised invoice through the app " + r.text[:200])
    pay = one("SELECT id FROM office_payments WHERE doc_id=? ORDER BY id DESC LIMIT 1", (inv,))
    ok(pay, "... the payment row")
    pay = (pay or {}).get("id")

    # ---------------------------------------------------------------- the positions
    items_before = [dict(x) for x in free("SELECT * FROM office_doc_items WHERE doc_id=? ORDER BY id", (inv,)).fetchall()]
    for what, sql, args in (("its title", "UPDATE office_doc_items SET title=? WHERE id=?", ("changed", its[0])),
                            ("its rate", "UPDATE office_doc_items SET rate=? WHERE id=?", (1, its[1])),
                            ("its net", "UPDATE office_doc_items SET net=? WHERE id=?", ("1.00", its[1])),
                            ("moved to a draft", "UPDATE office_doc_items SET doc_id=? WHERE id=?", (draft, its[1])),
                            ("a draft's position moved in", "UPDATE office_doc_items SET doc_id=? WHERE id=?", (inv, dits[0])),
                            ("a new position", "INSERT INTO office_doc_items(doc_id, org_id, title) VALUES(?,?,?)", (inv, oid, "added")),
                            ("a DELETE", "DELETE FROM office_doc_items WHERE id=?", (its[1],))):
        e = guarded(sql, args)
        ok(LOCKED in e, f"#6467: a position of a finalised invoice, {what}: refused by the database {e[:200]!r}")
    ok([dict(x) for x in free("SELECT * FROM office_doc_items WHERE doc_id=? ORDER BY id", (inv,)).fetchall()] == items_before,
       "#6467: the positions are unchanged after the refused statements")
    ok(guarded("UPDATE office_doc_items SET cost=cost+1 WHERE id=?", (its[0],)) == "", "#6467: the purchase price stays free")
    ok(guarded("UPDATE office_doc_items SET title=title WHERE id=?", (its[0],)) == "", "#6467: the same value again is no change")
    ok(guarded("UPDATE office_doc_items SET title='still a draft' WHERE id=?", (dits[0],)) == "", "#6467: a draft's position stays free")
    r = S.put(B + f"{D}/{draft}/items", json={"items": [{"title": "Edit", "qty": 1, "rate": 500}]})
    ok(r.ok, "#6467: a draft's positions are saved through the app " + r.text[:200])

    # ---------------------------------------------------------------- the payments
    p_before = one("SELECT * FROM office_payments WHERE id=?", (pay,))
    for what, sql, args in (("its amount", "UPDATE office_payments SET amount=? WHERE id=?", (1, pay)),
                            ("its date", "UPDATE office_payments SET date=? WHERE id=?", ("2001-01-01", pay)),
                            ("a DELETE", "DELETE FROM office_payments WHERE id=?", (pay,))):
        e = guarded(sql, args)
        ok(BOOKED in e, f"#6467: a payment, {what}: refused by the database {e[:200]!r}")
    ok(one("SELECT * FROM office_payments WHERE id=?", (pay,)) == p_before, "#6467: the payment is unchanged")
    ok(guarded("UPDATE office_payments SET bank_tx_id=? WHERE id=?", (987654, pay)) == "", "#6467: the bank line of a payment stays free")
    free("UPDATE office_payments SET bank_tx_id=NULL WHERE id=?", (pay,))

    # ---------------------------------------------------------------- the office log
    fin = one("SELECT id FROM office_doc_log WHERE doc_id=? AND action='finalize'", (inv,))["id"]
    for what, sql, args in (("its detail", "UPDATE office_doc_log SET detail='{}' WHERE id=?", (fin,)),
                            ("its action", "UPDATE office_doc_log SET action='open' WHERE id=?", (fin,)),
                            ("its document", "UPDATE office_doc_log SET doc_id=? WHERE id=?", (draft, fin)),
                            ("a DELETE", "DELETE FROM office_doc_log WHERE id=?", (fin,))):
        e = guarded(sql, args)
        ok(KEPT in e, f"#6467: the finalise entry, {what}: refused by the database {e[:200]!r}")
    rd = free("INSERT INTO office_doc_log(org_id, doc_id, at, action, target, detail) VALUES(?,?,?,?,?,?) RETURNING id",
              (oid, inv, OLD, "pdf", "doc", "{}")).fetchone()[0]
    ok(guarded("DELETE FROM office_doc_log WHERE id=?", (rd,)) == "", "#6467: a read entry may go")
    ag = free("INSERT INTO office_doc_log(org_id, doc_id, at, action, target, detail) VALUES(?,NULL,?,?,?,?) RETURNING id",
              (oid, OLD, "agent_write", "doc", "{}")).fetchone()[0]
    ok(guarded("UPDATE office_doc_log SET doc_id=? WHERE id=?", (draft, ag)) == "", "#6467: an agent's log line learns its draft once (agentdocs)")
    e = guarded("UPDATE office_doc_log SET doc_id=? WHERE id=?", (inv, ag))
    ok(KEPT in e, f"#6467: ... but not a second time {e[:200]!r}")

    # ---------------------------------------------------------------- the ways that keep running
    ok(guarded("DELETE FROM office_services WHERE id=?", (sv,)) == "", "#6467: a service deleted for good (the purge) goes through")
    ok(one("SELECT service_id FROM office_doc_items WHERE id=?", (its[0],))["service_id"] is None, "#6467: ... service_id emptied (SET NULL)")
    inv2 = doc()
    r = S.post(B + f"{D}/{inv2}/credit")
    ok(r.status_code == 201, "#6467: a credit note of a finalised invoice " + r.text[:200])
    if r.status_code == 201:
        r = S.post(B + f"{D}/{r.json()['id']}/finalize")
        ok(r.ok, "#6467: the credit note finalised " + r.text[:200])
    tri = doc(trial=True)
    r = S.delete(B + f"{D}/{tri}")
    ok(r.ok, "#6467: a finalised trial invoice is deleted with its positions " + r.text[:200])
    ok(one("SELECT count(*) AS n FROM office_doc_items WHERE doc_id=?", (tri,))["n"] == 0, "#6467: ... its positions went with it")

    # ---------------------------------------------------------------- the chain: version 2 for a new link
    ok(head["pdf_sha256"] and head["chain_seq"] and head["chain_ver"] == 2, f"#6467: a new link has version 2 and its stored PDF's checksum {head}")
    newest = doc(title="Newest " + who)
    ch = S.get(B + OFC + "/log/chain").json()
    ok(ch.get("ok") is True and ch.get("count", 0) >= 3, f"#6467: the chain is intact {ch}")
    return oid, inv, newest


OA, INV, NEWEST = run(A, "organisation")
OF, INVF, _NF = run(Fr, "freelancer")

# ---------------------------------------------------------------- in-app ways: prune, name fill, trim (the app's own connection)
rd = free("INSERT INTO office_doc_log(org_id, doc_id, at, action, target, detail) VALUES(?,?,?,?,?,?) RETURNING id",
          (OA, INV, OLD, "open", "doc", "{}")).fetchone()[0]
out = py("""
from kalmido.notify.push import fx2_office_log_prune
print(json.dumps({'n': fx2_office_log_prune(c, force=True)}))
""")
check(out.get("n", 0) >= 1 and one("SELECT id FROM office_doc_log WHERE id=?", (rd,)) is None, f"#6467: the prune of read entries runs (push.py) {out}")
free("UPDATE office_doc_log SET user_name='' WHERE doc_id=? AND action='finalize'", (INV,))
free("DELETE FROM settings WHERE key='migr_odl6470'")
out = py("""
from kalmido.office.ledger import ofx_log_names_fill
ofx_log_names_fill(c)
c.commit()
print(json.dumps({'ok': 1}))
""")
nm = one("SELECT user_name FROM office_doc_log WHERE doc_id=? AND action='finalize'", (INV,))
check(out.get("ok") and nm and nm["user_name"], f"#6467: the one-time name fill of #6470 runs past the log's trigger {out} {nm}")
sg = free("INSERT INTO office_doc_log(org_id, doc_id, at, action, target, detail) VALUES(?,?,?,?,?,?) RETURNING id",
          (OA, INV, OLD, "signoff_accepted", "doc", json.dumps({"email": "kunde@example.test", "name": "Kunde"}))).fetchone()[0]
out = py("""
from kalmido.office.signoff import sig_log_trim
n, left = sig_log_trim(c)
c.commit()
print(json.dumps({'n': n, 'left': left}))
""")
det = one("SELECT detail FROM office_doc_log WHERE id=?", (sg,))
check(out.get("n", 0) >= 1 and det and "kunde@example.test" not in det["detail"], f"#6467: the trim of #2561 runs past the log's trigger {out} {det}")

# ---------------------------------------------------------------- the chain versions
out = py(f"""
from kalmido.office.chain import hch_canon, hch_hash, hch_heads
d = c.execute("SELECT * FROM office_docs WHERE id=?", ({NEWEST},)).fetchone()
v1, v2 = hch_canon(c, {OA}, d, 1), hch_canon(c, {OA}, d, 2)
c.execute("SELECT set_config('kalmido.locked_ok', 'on', true)")  # a link as 2.531 made it (version 1, core/migrations.d/4598.py)
c.execute("UPDATE office_docs SET chain_ver=NULL, chain_hash=? WHERE id=?", (hch_hash(d['chain_prev'] or '', v1), {NEWEST}))
c.commit()
print(json.dumps({{'differ': v1 != v2, 'sha_in_v2': d['pdf_sha256'] in v2, 'sha_in_v1': d['pdf_sha256'] in v1, 'heads': hch_heads(c, {OA})}}))
""")
check(out.get("differ") and out.get("sha_in_v2") and not out.get("sha_in_v1"), f"#6467: version 2 holds the PDF's checksum, version 1 not {out}")
ch = A.get(B + OFC + "/log/chain").json()
check(ch.get("ok") is True, f"#6467: a link made with version 1 stays valid {ch}")
nw = one("SELECT chain_key, chain_seq, chain_hash, pdf_sha256 FROM office_docs WHERE id=?", (NEWEST,))
hd = [h for h in out.get("heads") or [] if h.get("chain") == nw["chain_key"]]
check(hd and hd[0]["id"] == NEWEST and hd[0]["seq"] == nw["chain_seq"] and hd[0]["hash"] == nw["chain_hash"] and hd[0]["ver"] == 1,
      f"#6467: hch_heads names the head of the series {out.get('heads')} {nw}")
free("UPDATE office_docs SET pdf_sha256=? WHERE id=?", ("1" * 64, NEWEST))
ch = A.get(B + OFC + "/log/chain").json()
check(ch.get("ok") is True, f"#6467: ... and does not cover the checksum (as before) {ch}")
free("UPDATE office_docs SET pdf_sha256=? WHERE id=?", (nw["pdf_sha256"], NEWEST))
sha = one("SELECT pdf_sha256 FROM office_docs WHERE id=?", (INV,))["pdf_sha256"]
free("UPDATE office_docs SET pdf_sha256=? WHERE id=?", ("0" * 64, INV))
ch = A.get(B + OFC + "/log/chain").json()
fb = ch.get("first_bad") or {}
check(ch.get("ok") is False and fb.get("id") == INV and fb.get("reason") == "data",
      f"#6467: a changed PDF checksum breaks a version-2 link {ch}")
check(Fr.get(B + OFC + "/log/chain").json().get("ok") is True, "#6467: the other office's chain stays intact")

# ---------------------------------------------------------------- the watchdog: one alert, one log line, then quiet
WD = """
from kalmido.office.chain import hch_watch_tick
from kalmido.notify.alerts import _AA
n = hch_watch_tick(c, force=True)
print(json.dumps({'n': n, 'q': [x[1] for x in _AA['q'] if x[0] == 'security' and str(x[1]).startswith('office_chain:')]}))
"""
w1 = py(WD)
check(w1.get("n") == 1 and w1.get("q") == [f"office_chain:{OA}"], f"#6467: the watchdog reports the new break once (admin alert) {w1}")
lines = free("SELECT doc_id, user_id FROM office_doc_log WHERE org_id=? AND action='chain_broken'", (OA,)).fetchall()
check(len(lines) == 1 and lines[0]["doc_id"] == INV and lines[0]["user_id"] is None, f"#6467: ... and one line in the office log {lines}")
check(not free("SELECT 1 FROM office_doc_log WHERE org_id=? AND action='chain_broken'", (OF,)).fetchall(), "#6467: ... nothing in the intact office")
w2 = py(WD)
check(w2.get("n") == 0 and not w2.get("q"), f"#6467: the next day the same break says nothing again {w2}")
check(len(free("SELECT 1 FROM office_doc_log WHERE org_id=? AND action='chain_broken'", (OA,)).fetchall()) == 1, "#6467: ... still one log line")
log = A.get(B + OFC + "/log").json().get("log") or []
check(any(x.get("action") == "chain_broken" for x in log), "#6467: the admin sees the line in the office log")
free("UPDATE office_docs SET pdf_sha256=? WHERE id=?", (sha, INV))
w3 = py(WD)
check(w3.get("n") == 0 and A.get(B + OFC + "/log/chain").json().get("ok") is True, f"#6467: intact again, nothing new {w3}")

# ---------------------------------------------------------------- 2.1333.0 (#6770): unreadable link, 3 days, savepoint
# the key cannot open the first invoice of its chain now (OrgCryptError, as a key from another backup); a later link of the same
# chain is changed in the database (reason link) -- before #6770 the check stopped at the unreadable one and never saw it
ch_inv = one("SELECT chain_key, chain_seq FROM office_docs WHERE id=?", (INV,))
LAST = one("SELECT id, chain_prev FROM office_docs WHERE org_id=? AND chain_key=? AND chain_seq>? ORDER BY chain_seq DESC LIMIT 1",
           (OA, ch_inv["chain_key"], ch_inv["chain_seq"]))
check(LAST is not None, f"#6770: the chain of the invoice has a later link {ch_inv}")
LAST = LAST or {"id": 0, "chain_prev": ""}
UNREAD = f"""
from kalmido.office import chain
from kalmido.core.orgcrypt import OrgCryptError
from kalmido.notify.alerts import _AA
_dec = chain.oc_dec_fields
def dec(c2, oid, table, r):
    if r['id'] == {INV}:
        raise OrgCryptError('test: the key cannot open it now')
    return _dec(c2, oid, table, r)
chain.oc_dec_fields = dec
"""
free("UPDATE office_docs SET chain_prev=? WHERE id=?", ("f" * 64, LAST["id"]))
u1 = py(UNREAD + """
res = chain.hch_check(c, %d)
n = chain.hch_watch_tick(c, force=True)
print(json.dumps({'res': res, 'n': n, 'q': [x[1] for x in _AA['q'] if x[0] == 'security']}))
""" % OA)
res = u1.get("res") or {}
check((res.get("first_bad") or {}).get("id") == LAST["id"] and (res.get("first_bad") or {}).get("reason") == "link"
      and (res.get("unreadable") or {}).get("id") == INV and res.get("ok") is False,
      f"#6770: the check goes on behind the unreadable invoice and names the later break {u1}")
check(u1.get("n") == 1 and u1.get("q") == [f"office_chain:{OA}"], f"#6770: ... the watchdog reports that break (no unreadable alert on day 1) {u1}")
lines = free("SELECT doc_id FROM office_doc_log WHERE org_id=? AND action='chain_broken' ORDER BY id", (OA,)).fetchall()
check([x["doc_id"] for x in lines][-1:] == [LAST["id"]], f"#6770: ... with a log line on the later document {[dict(x) for x in lines]}")
free("UPDATE office_docs SET chain_prev=? WHERE id=?", (LAST["chain_prev"], LAST["id"]))
# day 2 (the mark says: first seen yesterday) -> still quiet; day 3 -> one alert of its own; again the same day -> quiet
DAYS = UNREAD + """
from datetime import timedelta
from kalmido.core.db import gset, gsetting, local_now
t = local_now().date()
m = json.loads(gsetting(c, chain.HCH_UNREAD_KEY) or '{}')
e = m.get('%d') or {}
e.update({'since': (t - timedelta(days=%d)).isoformat(), 'last': (t - timedelta(days=%d)).isoformat()})
m['%d'] = e
gset(c, chain.HCH_UNREAD_KEY, json.dumps(m))
c.commit()
_AA['q'].clear()
n = chain.hch_watch_tick(c, force=True)
print(json.dumps({'n': n, 'q': [x[1] for x in _AA['q'] if x[0] == 'security'], 'mark': json.loads(gsetting(c, chain.HCH_UNREAD_KEY) or '{}')}))
"""
d2 = py(DAYS % (OA, 1, 1, OA))
check(d2.get("n") == 0 and not d2.get("q"), f"#6770: the second day in a row: no alert yet {d2}")
d3 = py(DAYS % (OA, 2, 1, OA))
check(d3.get("q") == [f"office_chain_unreadable:{OA}"] and (d3.get("mark") or {}).get(str(OA), {}).get("told") is True,
      f"#6770: the third day in a row: one admin alert of its own {d3}")
d4 = py(DAYS % (OA, 3, 1, OA))
check(not d4.get("q"), f"#6770: ... and only once {d4}")
d5 = py(DAYS % (OA, 9, 4, OA))  # last seen 4 days ago: a gap
m5 = (d5.get("mark") or {}).get(str(OA)) or {}
check(not d5.get("q") and m5.get("since") and m5.get("since") == m5.get("last") and m5.get("told") is False,
      f"#6770: a gap of days starts the count anew {d5}")
ok_again = py("""
from kalmido.office import chain
from kalmido.core.db import gsetting
n = chain.hch_watch_tick(c, force=True)
print(json.dumps({'n': n, 'mark': json.loads(gsetting(c, chain.HCH_UNREAD_KEY) or '{}'), 'ok': chain.hch_check(c, %d)['ok']}))
""" % OA)
check(ok_again.get("ok") is True and str(OA) not in (ok_again.get("mark") or {"x": 1}), f"#6770: readable again: the mark is gone {ok_again}")
# the savepoint: the first office reports a break, the second one's check fails -- the first one's log line stays
SP = """
from kalmido.office import chain
lo, hi = sorted([%d, %d])
did = c.execute("SELECT id FROM office_docs WHERE org_id=? AND chain_seq IS NOT NULL ORDER BY chain_seq LIMIT 1", (lo,)).fetchone()[0]
_check = chain.hch_check
def fake(c2, oid):
    if oid == hi:
        c2.execute("SELECT 1/0")  # a failing statement inside the transaction (Postgres aborts it without a savepoint)
    if oid == lo:
        return {'ok': False, 'count': 1, 'pending': 0, 'unreadable': None,
                'first_bad': {'id': did, 'number': '', 'chain': 'savepoint-test', 'seq': 1, 'reason': 'data'}}
    return _check(c2, oid)
chain.hch_check = fake
n = chain.hch_watch_tick(c, force=True)
print(json.dumps({'n': n, 'lo': lo, 'did': did}))
""" % (OA, OF)
BROKEN = "SELECT count(*) AS n FROM office_doc_log WHERE action='chain_broken'"
before = one(BROKEN)["n"]
sp = py(SP)
kept = one(BROKEN)["n"] - before
check(sp.get("n") == 1 and kept == 1, f"#6770: the failing check of one office keeps the other office's log line (savepoint) {sp} {kept}")
w4 = py(WD)
check(w4.get("n") == 0, f"#6770: the real check afterwards: nothing new, the test mark forgotten {w4}")

# ---------------------------------------------------------------- an organisation going for good takes its rows along
r = A.post(B + "/api/admin/orgs", json={"name": "Beta", "admin_id": ALICE})
check(r.status_code == 201, "a second organisation " + r.text[:200])
BETA = r.json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{BETA}"})
_ob, gone, _gn = run(A, "organisation Beta")
e = guarded("DELETE FROM orgs WHERE id=?", (BETA,))
check(e == "" and one("SELECT id FROM office_docs WHERE id=?", (gone,)) is None,
      f"#6467: the cascade of a deleted organisation passes the triggers (positions, payments, log) {e[:200]!r}")
check(one("SELECT count(*) AS n FROM office_doc_log WHERE org_id=?", (BETA,))["n"] == 0, "#6467: ... its log went with it")

print(f"p21309_b_office_gobd: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
