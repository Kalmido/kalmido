#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#6547): returned mails (delivery reports) and the mark of automatic mails. Own container (start.sh through kt.fresh, SMTP to
the stub of tests/stub_mail.py, the mail import's address set so the personal mail address exists). The reports go in through
integrations/mail.py mail_import in a second process of the container (as the instance mailbox's round hands them in).
Invented companies, people and addresses only. tenant-matrix: office  freelancer-matrix: office
 1. mail_auto (the one check of every mail input): a person's mail '', out-of-office 'reply', a newsletter 'auto', a delivery
    report / mailer-daemon 'report'; mail_bounce: the Message-ID + status of a DSN (text/rfc822-headers and message/rfc822), a
    delay is not failed, a read receipt is no bounce, a mailer-daemon text report is failed; the reason in words
 2. Auto-Submitted: an automatic mail (the test mail) carries auto-generated; a person's (an invoice, a letter) none
 3. per office (Alice's organisation, Frida without organisation): an invoice mailed keeps its Message-ID; its delivery report
    (5.1.1) marks it bounced with the reason (the document's mail.why, the history by the system), the person who sent it
    gets the News item (integfail, what mail_bounced_doc, opens the document); a second report changes nothing more; sending it
    again: sent, the reason gone. A letter mailed: its report marks the letter (mail.state bounced + why), News to the sender
 4. a delay report, a read receipt: nothing changes, the report is dropped; a report no sent mail matches: dropped and counted
    for the instance admins' alert (integration / bounce)
 5. an automatic answer (Auto-Submitted: auto-replied) to a task made from a mail is dropped (no comment); the same text
    without the header becomes the comment (red without the fix: the out-of-office note was a comment)
 6. a mail to a data protection sheet's code that is automatic is taken as 0 (never "signed (by mail)")
 7. an invitation by the instance admin: its Message-ID kept; its report clears sent_at ("e-mail not sent" in the list) and
    tells the inviting instance admin (mail_bounced_invite)
 8. a hub mail sent: its report marks send_state bounced with the reason as its note (instance mailbox; a workspace's mailbox
    only its own workspace's mails)
usage: p6547_bounce_test.py <datadir>"""
import json
import os
import shutil
import subprocess
import sys
import time

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, CT, DATA, check, dbx  # noqa: E402
from freelancer_fixture import FEATURES, freelancer  # noqa: E402

OF = "/api/office"
D = OF + "/docs"
L = OF + "/letters"
COMPANY = {"name": "Beispiel Film GmbH", "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE", "email": "hallo@beispiel.example",
           "vat_id": "DE123456789", "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}
ENV = {"KALMIDO_SMTP_HOST": "127.0.0.1", "KALMIDO_SMTP_PORT": "1025", "KALMIDO_SMTP_TLS": "none", "KALMIDO_MAIL_FROM": "kalmido@example.test",
       "KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_MAIL_ADDRESS": "tasks@example.test", "KALMIDO_IMAP_HOST": "127.0.0.1",
       "KALMIDO_IMAP_PORT": "1143", "KALMIDO_IMAP_SSL": "0", "KALMIDO_IMAP_USER": "kalmido", "KALMIDO_IMAP_PASSWORD": "secret",
       "KALMIDO_IMAP_INTERVAL": "86400"}

kt.fresh(env=ENV, prefix="P6547")
os.makedirs(os.path.join(DATA, "mail", "in"), exist_ok=True)
shutil.copy(os.path.join(N, "stub_mail.py"), DATA)
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/stub_mail.py"], check=True)
kt.until(lambda: subprocess.run(["docker", "exec", CT, "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 1025), 1)"],
                                capture_output=True).returncode == 0, 20)


def py(code):
    """Runs code in a second process of the container (no loops); the last line = JSON."""
    r = None
    for _try in range(3):  # the import may meet the running server's start-up DDL (deadlock): try again
        r = subprocess.run(["docker", "exec", "-i", "-w", "/app", "-e", "TASKS_WATCHDOG=0", "-e", "KALMIDO_ROLE=web", CT, "python", "-"],
                           input="import app\n" + code, capture_output=True, text=True, timeout=300)
        if "DeadlockDetected" not in r.stdout + r.stderr:
            break
        time.sleep(2)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        print((r.stdout + r.stderr)[-3000:], flush=True)
        return {}


IMPORT = """
import json
from kalmido.core.db import connect
from kalmido.integrations import mail as M
from kalmido.notify import alerts as AL
raw = {raw!r}.encode()
c = connect()
try:
    res = M.mail_import(c, raw)
    c.commit()
finally:
    c.close()
b = AL._AA["b"].get(("integration", "bounce"))
print(json.dumps({{"drop": res is M.MAIL_DROP, "res": repr(res), "unmatched": b["n"] if b else 0}}))
"""


def mail_in(raw):
    return py(IMPORT.format(raw=raw))


def dsn(mid, status="5.1.1", action="failed", rcpt="kunde@example.com", headers=True):
    """A delivery report of the instance's server (RFC 3464) about the mail mid."""
    orig = (f"Content-Type: text/rfc822-headers\n\nFrom: kalmido@example.test\nTo: {rcpt}\nSubject: Rechnung\nMessage-ID: {mid}\n" if headers
            else f"Content-Type: message/rfc822\n\nFrom: kalmido@example.test\nTo: {rcpt}\nSubject: Rechnung\nMessage-ID: {mid}\n\nText\n")
    return ("From: Mail Delivery System <MAILER-DAEMON@mx.example.test>\nTo: kalmido@example.test\nSubject: Undelivered Mail Returned to Sender\n"
            f"Message-ID: <dsn-{time.time_ns()}@mx.example.test>\nAuto-Submitted: auto-replied\nMIME-Version: 1.0\n"
            'Content-Type: multipart/report; report-type=delivery-status; boundary="BB"\n\n'
            "--BB\nContent-Type: text/plain\n\nThis is the mail system. Your message could not be delivered.\n\n"
            "--BB\nContent-Type: message/delivery-status\n\nReporting-MTA: dns; mx.example.test\n\n"
            f"Final-Recipient: rfc822; {rcpt}\nAction: {action}\nStatus: {status}\nDiagnostic-Code: smtp; 550 {status} User unknown\n\n"
            f"--BB\n{orig}\n--BB--\n")


def outbox():
    try:
        return [json.loads(x) for x in open(os.path.join(DATA, "mail", "out.jsonl"), encoding="utf-8")]
    except OSError:
        return []


def news(uid, what):
    return [json.loads(r[0]) for r in dbx("SELECT data::text FROM notifications WHERE user_id=? AND kind='integfail' ORDER BY id", (uid,))
            if json.loads(r[0]).get("what") == what]


A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = kt.me_id(A)
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A)
Fr.patch(B + "/api/settings", json={"workspace": "private"})
kt.proved()

# ---------------------------------------------------------------- 1. the one check and the report's reading
S1 = {"dsn": dsn("<orig1@example.test>"), "dsn2": dsn("<orig2@example.test>", headers=False, status="5.7.1"),
      "delay": dsn("<orig3@example.test>", action="delayed", status="4.4.1")}
r1 = py("S1 = " + repr(S1) + r'''
import json, email
from email import policy
from kalmido.integrations import mail as M
def m(s):
    return email.message_from_string(s, policy=policy.default)
person = m("From: Kim <kim@example.com>\nSubject: Hallo\n\nText\n")
ooo = m("From: Kim <kim@example.com>\nAuto-Submitted: auto-replied\nSubject: Abwesend\n\nBin weg\n")
ooo2 = m("From: kim@example.com\nX-Autoreply: yes\nSubject: Abwesend\n\nBin weg\n")
news_ = m("From: shop@example.com\nPrecedence: bulk\nSubject: Angebote\n\nText\n")
gen = m("From: shop@example.com\nAuto-Submitted: auto-generated\nSubject: Ihre Rechnung\n\nText\n")
no = m("From: kim@example.com\nAuto-Submitted: no\nSubject: x\n\nText\n")
daemon = m("From: MAILER-DAEMON@mx.example.test\nSubject: failure notice\n\nHi. This is the qmail-send program.\n<kunde@example.com>:\n550 5.2.2 mailbox full\n--- Below this line is a copy of the message.\nMessage-ID: <q1@example.test>\nSubject: x\n")
dsn, dsn2, delay = m(S1["dsn"]), m(S1["dsn2"]), m(S1["delay"])
mdn = m('From: kim@example.com\nContent-Type: multipart/report; report-type=disposition-notification; boundary="X"\n\n--X\nContent-Type: text/plain\n\nRead\n--X\nContent-Type: message/disposition-notification\n\nDisposition: manual-action/MDN-sent-manually; displayed\n--X--\n')
print(json.dumps({"auto": [M.mail_auto(x) for x in (person, ooo, ooo2, news_, gen, no, daemon, dsn)],
                  "b": [M.mail_bounce(x) for x in (person, dsn, dsn2, delay, mdn, daemon)],
                  "why": [M.mail_bounce_why(x, lg="en") for x in ("5.1.1", "5.2.2", "5.7.1", "5.4.4", "5.3.0", "")],
                  "hdr": [str(M.mail_message("x@example.com", "s", "t").get("Auto-Submitted")), str(M.mail_message("x@example.com", "s", "t", auto=False).get("Auto-Submitted"))]}))
''')
check(r1.get("auto") == ["", "reply", "reply", "auto", "auto", "", "report", "report"], f"1: mail_auto {r1.get('auto')}")
b = r1.get("b") or [None] * 6
check(b[0] is None, f"1: a person's mail is no report {b[0]}")
check(b[1] == {"mid": "<orig1@example.test>", "code": "5.1.1", "failed": True}, f"1: DSN with text/rfc822-headers {b[1]}")
check(b[2] == {"mid": "<orig2@example.test>", "code": "5.7.1", "failed": True}, f"1: DSN with message/rfc822 {b[2]}")
check(b[3] and b[3]["mid"] == "<orig3@example.test>" and not b[3]["failed"], f"1: a delay is not failed {b[3]}")
check(b[4] == {"mid": "", "code": "", "failed": False}, f"1: a read receipt is no bounce {b[4]}")
check(b[5] == {"mid": "<q1@example.test>", "code": "5.2.2", "failed": True}, f"1: a mailer-daemon text report {b[5]}")
check(r1.get("why") == ["the address does not exist (5.1.1)", "the mailbox is full (5.2.2)",
                        "the receiving server refused the e-mail (sender check or spam filter) (5.7.1)",
                        "the domain of the address takes no e-mail (5.4.4)", "the receiving server returned it (5.3.0)",
                        "the receiving server returned it"], f"1: the reason in words {r1.get('why')}")
check(r1.get("hdr") == ["auto-generated", "None"], f"1: mail_message marks an automatic mail only {r1.get('hdr')}")

# ---------------------------------------------------------------- 2. the mark on the mails that go out
n0 = len(outbox())
r = Fr.post(B + "/api/me/mail/test", json={})  # (Frida has a proved address; Alice of the setup none)
o = outbox()[n0:]
check(r.ok and len(o) == 1 and "Auto-Submitted: auto-generated" in o[0]["raw"], f"2: the test mail is marked automatic {r.status_code} {r.text[:120]}")


# ---------------------------------------------------------------- 3. an office's invoice and letter
def office(s, who, uid):
    def ok(cond, what):
        check(cond, f"3 {who}: {what}")

    assert s.put(B + OF + "/settings", json={"company_fields": COMPANY}).ok
    r = s.post(B + "/api/clients", json={"name": f"Kunde {who} GmbH", "street": "Weg 2", "zip": "10115", "city": "Berlin", "country": "DE",
                                         "email": f"kunde-{who}@example.com"})
    assert r.ok, r.text
    cl = r.json()["id"]
    r = s.post(B + D, json={"kind": "invoice", "client_id": cl, "service_from": kt.today().isoformat(), "items": [{"title": "Schnitt", "qty": 1, "rate": 100}]})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    assert s.post(B + f"{D}/{did}/finalize").ok
    n0 = len(outbox())
    r = s.post(B + f"{D}/{did}/send", json={"to": f"kunde-{who}@example.com"})
    o = outbox()[n0:]
    mid = (dbx("SELECT mail_msg_id FROM office_docs WHERE id=?", (did,)) or [[""]])[0][0]
    ok(r.ok and mid.startswith("<") and len(o) == 1 and f"Message-ID: {mid}" in o[0]["raw"], f"the invoice keeps its Message-ID {r.status_code} {mid!r}")
    ok("Auto-Submitted" not in o[0]["raw"] if o else False, "a person's invoice mail carries no Auto-Submitted")
    j = mail_in(dsn(mid, rcpt=f"kunde-{who}@example.com"))
    d = s.get(B + f"{D}/{did}").json()
    ok(j.get("drop") and (d.get("mail") or {}).get("state") == "bounced" and d["mail"].get("why") == "the address does not exist (5.1.1)",
       f"the report marks it bounced with the reason {j} {d.get('mail')}")
    h = dbx("SELECT user_id, via, vals_after::text FROM obj_history WHERE kind='office_doc' AND ref_id=? AND action='mail' ORDER BY id", (did,))
    ok(h and h[-1][0] is None and h[-1][1] == "system" and json.loads(h[-1][2]).get("mail_state") == "bounced", f"the history: bounced by the system {h}")
    nw = news(uid, "mail_bounced_doc")
    ok(len(nw) == 1 and nw[0].get("go") == f"office/invoices/{did}" and "(5.1.1)" in nw[0].get("text", ""), f"the sender's News item {nw}")
    mail_in(dsn(mid, rcpt=f"kunde-{who}@example.com"))
    ok(len(news(uid, "mail_bounced_doc")) == 1, "a second report of the same mail: no second News item")
    r = s.post(B + f"{D}/{did}/send", json={"to": f"kunde-{who}-neu@example.com"})
    d = s.get(B + f"{D}/{did}").json()
    ok(r.ok and d.get("mail", {}).get("state") == "sent" and "why" not in d["mail"], f"sent again: sent, the reason gone {r.status_code} {d.get('mail')}")
    # a letter by e-mail
    r = s.post(B + L, json={"rcpt_name": "Amt fuer Beispiele", "rcpt_address": "Musterweg 1\n12345 Musterstadt", "rcpt_email": f"amt-{who}@example.com",
                            "subject": "Antrag", "body": "Sehr geehrte Damen und Herren, ein Absatz."})
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    r = s.post(B + f"{L}/{lid}/send-mail", json={})
    lmid = (dbx("SELECT msg_id FROM office_letters WHERE id=?", (lid,)) or [[""]])[0][0]
    ok(r.ok and lmid.startswith("<"), f"the letter went by mail {r.status_code} {r.text[:160]}")
    raw = next((x["raw"] for x in outbox() if f"Message-ID: {lmid}" in x["raw"]), "")
    ok(raw and "Auto-Submitted" not in raw, "a letter carries no Auto-Submitted")
    mail_in(dsn(lmid, status="5.2.2", rcpt=f"amt-{who}@example.com"))
    lt = s.get(B + f"{L}/{lid}").json()
    ok((lt.get("mail") or {}).get("state") == "bounced" and lt["mail"].get("why") == "the mailbox is full (5.2.2)", f"the letter is marked {lt.get('mail')}")
    ok(len(news(uid, "mail_bounced_letter")) == 1, f"the letter's sender hears it {news(uid, 'mail_bounced_letter')}")
    return did


DA = office(A, "alpha", ALICE)
DF = office(Fr, "frida", FID)

# ---------------------------------------------------------------- 4. a delay, a read receipt, a report nobody's mail matches
mid = dbx("SELECT mail_msg_id FROM office_docs WHERE id=?", (DA,))[0][0]
j = mail_in(dsn(mid, action="delayed", status="4.4.1"))
check(j.get("drop") and A.get(B + f"{D}/{DA}").json().get("mail", {}).get("state") == "sent", f"4: a delay changes nothing, dropped {j}")
j = mail_in('From: kunde@example.com\nTo: kalmido@example.test\nMessage-ID: <mdn1@example.com>\nContent-Type: multipart/report; report-type=disposition-notification; boundary="X"\n\n'
            '--X\nContent-Type: text/plain\n\nRead\n--X\nContent-Type: message/disposition-notification\n\nDisposition: manual-action/MDN-sent-manually; displayed\n--X--\n')
check(j.get("drop") and j.get("unmatched") == 0, f"4: a read receipt is dropped, not counted {j}")
j = mail_in(dsn("<nobody-knows@example.test>"))
check(j.get("drop") and j.get("unmatched") == 1, f"4: a report no mail matches: dropped and counted for the alert {j}")

# ---------------------------------------------------------------- 5. an automatic answer to a task made from a mail
r = A.post(B + "/api/me/mail/token", json={})
addr = r.json().get("address", "") if r.ok else ""
check("+" in addr, f"5: the personal mail address {r.status_code} {addr}")
src = f"From: Kim <kim@example.com>\nTo: {addr}\nSubject: Bitte um Rueckruf\nMessage-ID: <p6547-src@example.com>\n\nBitte melden.\n"
j = mail_in(src)
tid = int(j.get("res") or 0) if str(j.get("res") or "").isdigit() else 0
check(tid > 0, f"5: the mail became a task {j}")
ooo = (f"From: Kim <kim@example.com>\nTo: {addr}\nSubject: Abwesend: Bitte um Rueckruf\nMessage-ID: <p6547-ooo@example.com>\n"
       "In-Reply-To: <p6547-src@example.com>\nAuto-Submitted: auto-replied\n\nIch bin bis Montag nicht im Buero.\n")
j = mail_in(ooo)
n_com = dbx("SELECT COUNT(*) FROM obj_comments WHERE kind='task' AND ref_id=?", (tid,))[0][0]
n_tasks = dbx("SELECT COUNT(*) FROM tasks WHERE tt_id=?", ("mail:<p6547-ooo@example.com>",))[0][0]
check(j.get("drop") and n_com == 0 and n_tasks == 0, f"5: the out-of-office answer is dropped: no comment, no task {j} {n_com} {n_tasks}")
j = mail_in(ooo.replace("Auto-Submitted: auto-replied\n", "").replace("p6547-ooo", "p6547-real"))
n_com = dbx("SELECT COUNT(*) FROM obj_comments WHERE kind='task' AND ref_id=?", (tid,))[0][0]
check(n_com == 1, f"5: the same answer by a person is the comment {j} {n_com}")

# ---------------------------------------------------------------- 6. a data protection sheet's code in an automatic mail
r6 = py(r'''
import json, email
from email import policy
from kalmido.core.db import connect
from kalmido.office.privacy import dsb_mail_import
c = connect()
try:
    m = email.message_from_string("From: kunde@example.com\nTo: tasks@example.test\nSubject: Abwesend: [DS-ABCDEFGHJKLM] Datenschutz\nAuto-Submitted: auto-replied\n\nWeg\n", policy=policy.default)
    p = email.message_from_string("From: kunde@example.com\nTo: tasks@example.test\nSubject: Re: [DS-ABCDEFGHJKLM] Datenschutz\n\nAnbei\n", policy=policy.default)
    print(json.dumps({"auto": dsb_mail_import(c, m, b"x"), "person": dsb_mail_import(c, p, b"y")}))
finally:
    c.rollback()
    c.close()
''')
check(r6.get("auto") == 0 and r6.get("person") is None, f"6: an automatic mail never reaches a sheet (0), a person's is looked up {r6}")

# ---------------------------------------------------------------- 7. the invitation of the instance admin
r = A.post(B + "/api/users", json={"username": "neu", "display_name": "Neu", "email": "neu@example.com", "orgs": [], "invite": True})
check(r.ok, f"7: invited {r.status_code} {r.text[:160]}")
NID = r.json().get("id") if r.ok else 0
kt.until(lambda: (dbx("SELECT msg_id FROM user_invites WHERE user_id=?", (NID,)) or [[""]])[0][0].startswith("<"), 30)
row = dbx("SELECT msg_id, sent_at FROM user_invites WHERE user_id=?", (NID,))
check(row and row[0][0].startswith("<") and row[0][1], f"7: the invitation keeps its Message-ID and sent_at {row}")
if row and row[0][0]:
    mail_in(dsn(row[0][0], rcpt="neu@example.com"))
    row = dbx("SELECT sent_at FROM user_invites WHERE user_id=?", (NID,))
    us = A.get(B + "/api/users?all=1").json().get("users", [])
    u = next((x for x in us or [] if x.get("id") == NID), {})
    check(row and row[0][0] is None and u.get("invite_unsent") is True, f"7: the report clears sent_at, the list says not sent {row} {u.get('invite_unsent')}")
    check(len(news(ALICE, "mail_bounced_invite")) == 1, f"7: the inviting instance admin hears it {news(ALICE, 'mail_bounced_invite')}")

# ---------------------------------------------------------------- 8. a hub mail (instance mailbox: any; a workspace's mailbox: its own)
r8 = py(r'''
import json, email
from email import policy
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
from kalmido.hub.hubmail import hbm_bounce
c = connect()
out = {}
try:
    with system_ctx(c):
        for mid, ws in (("<hub1@example.test>", "u%(fid)d"), ("<hub2@example.test>", "u%(fid)d")):
            c.execute("INSERT INTO hub_mails(owner_id, ws, message_id, direction, send_state, created_at) VALUES(?,?,?,'out','',now())", (%(fid)d, ws, mid))
        out["other_ws"] = hbm_bounce(c, "<hub1@example.test>", "5.1.1", (None, "o999999"))
        out["own_ws"] = hbm_bounce(c, "<hub1@example.test>", "5.1.1", (None, "u%(fid)d"))
        out["instance"] = hbm_bounce(c, "<hub2@example.test>", "", None)
        out["rows"] = [[r[0], r[1]] for r in c.execute("SELECT send_state, note FROM hub_mails WHERE message_id IN ('<hub1@example.test>', '<hub2@example.test>') ORDER BY message_id")]
    c.commit()
finally:
    c.close()
print(json.dumps(out))
''' % {"fid": FID})
check(r8.get("other_ws") is False and r8.get("own_ws") is True and r8.get("instance") is True, f"8: hub: another workspace's mailbox never, its own and the instance's yes {r8}")
check(r8.get("rows") == [["bounced", "Not delivered: the address does not exist (5.1.1)"], ["bounced", "Not delivered: the receiving server returned it"]],
      f"8: hub: send_state bounced, the reason as the note {r8.get('rows')}")
check(len(news(FID, "mail_bounced_hub")) == 2, f"8: hub: the sender hears it {news(FID, 'mail_bounced_hub')}")

sys.exit(kt.done("p6547_bounce"))
